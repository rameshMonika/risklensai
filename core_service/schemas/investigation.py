from pydantic import BaseModel


class InvestigationCreate(BaseModel):
    question: str


class EvidenceItem(BaseModel):
    symbol: str
    title: str | None
    source_url: str | None


class InvestigationResponse(BaseModel):
    question: str
    answer: str
    trajectory: list[str]
    risk_results: dict[str, dict[str, float]]
    evidence: list[EvidenceItem]
    limitations: str | None
