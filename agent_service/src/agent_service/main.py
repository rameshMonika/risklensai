"""FastAPI app for the Agent service. Fully stateless, no database access
(see CLAUDE.md's Backend architecture) -- only reachable by Core, guarded by
a shared internal API key, not a user JWT.
"""

from contextlib import asynccontextmanager
from datetime import datetime

print("CHECKPOINT 1: stdlib imports done", flush=True)

from fastapi import Depends, FastAPI

print("CHECKPOINT 2: fastapi imported", flush=True)

from agent_service.core.mcp_manager import mcp_manager

print("CHECKPOINT 3: mcp_manager imported", flush=True)

from agent_service.core.security import verify_internal_api_key

print("CHECKPOINT 4: security imported", flush=True)

from agent_service.core.observability import configure_tracing

# Push LANGSMITH_* into os.environ (from .env / Settings) before the graph is
# imported and the first request runs, so LangChain/LangGraph auto-tracing picks
# it up. No-op when tracing is disabled.
configure_tracing()

from agent_service.graph.build import run_investigation

print("CHECKPOINT 5: graph.build imported (this pulls in nodes/guardrail/router/llm)", flush=True)

from agent_service.schemas.investigate import EvidenceOut, InvestigateRequest, InvestigateResponse

print("CHECKPOINT 6: schemas imported, main.py module body continuing", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await mcp_manager.connect_all()
    yield
    await mcp_manager.close_all()


app = FastAPI(title="Portfolio Risk Investigator - Agent Service", lifespan=lifespan)


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@app.post("/internal/investigate", response_model=InvestigateResponse, dependencies=[Depends(verify_internal_api_key)])
async def investigate(payload: InvestigateRequest) -> InvestigateResponse:
    holdings = [h.model_dump() for h in payload.holdings]
    final_state, trace_id = await run_investigation(
        payload.question, holdings, payload.start_date, payload.end_date
    )

    target = final_state.get("target_symbol") or final_state.get("news_target")
    evidence = [
        EvidenceOut(
            symbol=target,
            title=ev.get("title"),
            source_url=ev.get("url"),
            published_at=_parse_datetime(ev.get("published_date")),
            evidence_text=ev.get("content"),
        )
        for ev in final_state.get("news_evidence", [])
    ]

    return InvestigateResponse(
        intent=final_state.get("intent"),
        trajectory=final_state.get("agents_used", []),
        answer=final_state.get("answer", ""),
        risk_results=final_state.get("risk_results", {}),
        evidence=evidence,
        refused=final_state.get("refused", False),
        not_found=final_state.get("not_found", False),
        observability_trace_id=trace_id,
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.middleware("http")
async def force_json_charset(request, call_next):
    response = await call_next(request)
    if response.headers.get("content-type", "").startswith("application/json"):
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response
