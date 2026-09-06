from datetime import date

import httpx

from core_service.core.config import settings
from core_service.db.models import Holding


async def investigate(holdings: list[Holding], question: str, start_date: date, end_date: date) -> dict:
    """Calls Agent service's POST /internal/investigate. Returns the raw
    response dict (agent_service's InvestigateResponse shape: intent,
    trajectory, answer, risk_results, evidence, refused, not_found) --
    api/investigations.py maps this into the frontend-facing shape and
    persists it, this function's only job is the HTTP call.
    """
    payload = {
        "question": question,
        "holdings": [
            {"symbol": h.symbol, "quantity": float(h.quantity), "avg_cost": float(h.avg_cost)} for h in holdings
        ],
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
    }
    # A full investigation fans out to several MCP/API calls plus 2+ LLM calls
    # on gpt-oss-120b (a reasoning model), so the read budget is generous; a
    # genuinely-down agent still fails fast on the short connect timeout.
    timeout = httpx.Timeout(180.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.agent_service_url}/internal/investigate",
            json=payload,
            headers={"X-Internal-Api-Key": settings.internal_service_api_key},
        )
        response.raise_for_status()
        return response.json()
