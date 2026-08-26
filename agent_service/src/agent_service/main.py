"""FastAPI app for the Agent service. Fully stateless, no database access
(see CLAUDE.md's Backend architecture) -- only reachable by Core, guarded by
a shared internal API key, not a user JWT.
"""

from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI

from agent_service.core.mcp_manager import mcp_manager
from agent_service.core.security import verify_internal_api_key
from agent_service.graph.build import run_investigation
from agent_service.schemas.investigate import EvidenceOut, InvestigateRequest, InvestigateResponse


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
    final_state = await run_investigation(payload.question, holdings, payload.start_date, payload.end_date)

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
