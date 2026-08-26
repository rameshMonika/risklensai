from datetime import date
from typing import List, Optional, TypedDict


class InvestigationState(TypedDict):
    question: str
    start_date: date
    end_date: date

    intent: Optional[str]
    plan: List[str]           # ordered agent keys the Supervisor decided on, e.g. ["market", "risk", "answer"]
    step: int                 # index into plan of the next agent to dispatch to
    agents_used: List[str]    # Title-Case trajectory actually executed
    target_symbol: Optional[str]
    refused: bool
    not_found: bool

    holdings: list
    scope_symbols: List[str]
    prices: dict
    sectors: dict
    risk_results: dict
    news_target: Optional[str]
    news_evidence: list
    answer: str
