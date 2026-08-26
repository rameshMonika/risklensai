from datetime import date, datetime

from pydantic import BaseModel


class HoldingIn(BaseModel):
    symbol: str
    quantity: float
    avg_cost: float


class InvestigateRequest(BaseModel):
    question: str
    holdings: list[HoldingIn]
    start_date: date
    end_date: date


class EvidenceOut(BaseModel):
    symbol: str
    title: str | None
    source_url: str | None
    published_at: datetime | None
    evidence_text: str | None


class InvestigateResponse(BaseModel):
    intent: str | None
    trajectory: list[str]
    answer: str
    risk_results: dict
    evidence: list[EvidenceOut]
    refused: bool
    not_found: bool
