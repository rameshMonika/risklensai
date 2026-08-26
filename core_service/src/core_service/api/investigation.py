from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_service.api.deps import get_current_user
from core_service.api.portfolio import get_or_create_portfolio
from core_service.core.agent_client import investigate as call_agent
from core_service.db.models import Evidence, Holding, Investigation, InvestigationReport, User
from core_service.db.session import get_db
from core_service.schemas.investigation import EvidenceItem, InvestigationCreate, InvestigationResponse

router = APIRouter(prefix="/investigations", tags=["investigations"])

DEFAULT_LOOKBACK_DAYS = 90

# Metrics the frontend's flat Record<metric, Record<symbol, number>> rendering
# can display -- concentration/sector_exposure/correlation_matrix are nested
# differently and aren't sent to the frontend (see CLAUDE.md's risk_results note).
FLAT_RISK_METRICS = {"volatility", "max_drawdown"}


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@router.post("", response_model=InvestigationResponse, status_code=status.HTTP_201_CREATED)
async def create_investigation(
    payload: InvestigationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InvestigationResponse:
    portfolio = get_or_create_portfolio(db, current_user)
    holdings = list(db.scalars(select(Holding).where(Holding.portfolio_id == portfolio.id)))

    end_date = date.today()
    start_date = end_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)

    try:
        agent_result = await call_agent(holdings, payload.question, start_date, end_date)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Agent service request failed") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="Agent service unreachable") from exc

    if agent_result["refused"]:
        investigation_status = "refused"
    elif agent_result["not_found"]:
        investigation_status = "not_found"
    else:
        investigation_status = "completed"

    investigation = Investigation(
        portfolio_id=portfolio.id,
        query=payload.question,
        intent=agent_result.get("intent"),
        status=investigation_status,
        start_date=start_date,
        end_date=end_date,
        risk_results=agent_result.get("risk_results") or None,
    )
    db.add(investigation)
    db.flush()  # populates investigation.id for the FK rows below

    for ev in agent_result.get("evidence", []):
        db.add(Evidence(
            investigation_id=investigation.id,
            symbol=ev["symbol"],
            title=ev.get("title"),
            source_url=ev.get("source_url"),
            published_at=_parse_datetime(ev.get("published_at")),
            evidence_text=ev.get("evidence_text"),
        ))

    db.add(InvestigationReport(
        investigation_id=investigation.id,
        summary=agent_result["answer"],
        report_json=agent_result,
    ))
    db.commit()

    flat_risk_results = {
        metric: values
        for metric, values in (agent_result.get("risk_results") or {}).items()
        if metric in FLAT_RISK_METRICS
    }

    return InvestigationResponse(
        question=payload.question,
        answer=agent_result["answer"],
        trajectory=agent_result.get("trajectory", []),
        risk_results=flat_risk_results,
        evidence=[
            EvidenceItem(symbol=ev["symbol"], title=ev.get("title"), source_url=ev.get("source_url"))
            for ev in agent_result.get("evidence", [])
        ],
        limitations=None,
    )
