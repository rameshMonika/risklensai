from fastapi import Header, HTTPException, status

from agent_service.core.config import settings


def verify_internal_api_key(x_internal_api_key: str = Header(...)) -> None:
    """Guards POST /internal/investigate. Core sends X-Internal-Api-Key on
    every call; anyone without the shared secret gets rejected before the
    LangGraph pipeline (and its Groq/Alpha Vantage/Tavily quota) ever runs.
    """
    if x_internal_api_key != settings.internal_service_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid internal API key")
