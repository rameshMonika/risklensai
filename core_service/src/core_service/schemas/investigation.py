from pydantic import BaseModel


class InvestigationCreate(BaseModel):
    question: str


class EvidenceItem(BaseModel):
    symbol: str
    title: str | None
    source_url: str | None
    evidence_text: str | None


class ConcentrationResult(BaseModel):
    weights: dict[str, float]
    largest_holding_symbol: str
    largest_holding_weight: float


class InvestigationResponse(BaseModel):
    question: str
    answer: str
    status: str
    trajectory: list[str]
    # Metrics shaped as {symbol_or_sector: value} -- volatility, max_drawdown,
    # sector_exposure, loss_contribution all fit this flat shape.
    # concentration and correlation_matrix don't (see their own fields below),
    # so they're never in here.
    risk_results: dict[str, dict[str, float]]
    concentration: ConcentrationResult | None
    correlation_matrix: dict[str, dict[str, float]] | None
    evidence: list[EvidenceItem]
    limitations: str | None
