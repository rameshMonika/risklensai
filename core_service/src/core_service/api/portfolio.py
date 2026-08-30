import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_service.api.deps import get_current_user
from core_service.db.models import Holding, Portfolio, User
from core_service.db.session import get_db
import httpx

from core_service.core.config import settings
from core_service.schemas.portfolio import (
    HoldingCreate,
    HoldingResponse,
    HoldingUpdate,
    QuoteResult,
    SymbolSearchResult,
)


router = APIRouter(prefix="/portfolio", tags=["portfolio"])


def get_or_create_portfolio(db: Session, user: User) -> Portfolio:
    """V1 has no portfolio-selection UI, so each user implicitly has exactly
    one portfolio, created lazily on first use."""
    portfolio = db.scalar(select(Portfolio).where(Portfolio.user_id == user.id))
    if portfolio is None:
        portfolio = Portfolio(user_id=user.id, name=f"{user.name}'s Portfolio")
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
    return portfolio


def get_owned_holding(db: Session, holding_id: int, user: User) -> Holding:
    holding = db.get(Holding, holding_id)
    if holding is None or holding.portfolio.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Holding not found")
    return holding


@router.get("/holdings", response_model=list[HoldingResponse])
def list_holdings(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Holding]:
    portfolio = get_or_create_portfolio(db, current_user)
    return list(db.scalars(select(Holding).where(Holding.portfolio_id == portfolio.id)))


@router.post("/holdings", response_model=HoldingResponse, status_code=status.HTTP_201_CREATED)
def create_holding(
    payload: HoldingCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Holding:
    portfolio = get_or_create_portfolio(db, current_user)
    holding = Holding(
        portfolio_id=portfolio.id,
        symbol=payload.symbol.upper(),
        quantity=payload.quantity,
        avg_cost=payload.avg_cost,
    )
    db.add(holding)
    db.commit()
    db.refresh(holding)
    return holding


@router.put("/holdings/{holding_id}", response_model=HoldingResponse)
def update_holding(
    holding_id: int,
    payload: HoldingUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Holding:
    holding = get_owned_holding(db, holding_id, current_user)
    holding.symbol = payload.symbol.upper()
    holding.quantity = payload.quantity
    holding.avg_cost = payload.avg_cost
    db.commit()
    db.refresh(holding)
    return holding


@router.delete("/holdings/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_holding(
    holding_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    holding = get_owned_holding(db, holding_id, current_user)
    db.delete(holding)
    db.commit()


@router.get("/symbol-search", response_model=list[SymbolSearchResult])
async def search_symbols(q: str, current_user: User = Depends(get_current_user)) -> list[SymbolSearchResult]:
    """Live company/ticker search via Alpha Vantage SYMBOL_SEARCH, backing the
    Add Holding form's autocomplete. Requires auth (same as every other
    portfolio endpoint) so the API key/quota isn't exposed to anonymous callers.
    """
    query = q.strip()
    if len(query) < 2:
        return []

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            "https://www.alphavantage.co/query",
            params={"function": "SYMBOL_SEARCH", "keywords": query, "apikey": settings.alpha_vantage_api_key},
        )
    data = resp.json()
    matches = data.get("bestMatches", [])

    return [
        SymbolSearchResult(symbol=m["1. symbol"], name=m["2. name"])
        for m in matches
        if m.get("4. region") == "United States"
    ][:8]


async def _fetch_quote(client: httpx.AsyncClient, symbol: str) -> QuoteResult | None:
    resp = await client.get(
        "https://www.alphavantage.co/query",
        params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": settings.alpha_vantage_api_key},
    )
    price_str = resp.json().get("Global Quote", {}).get("05. price")
    if price_str is None:
        # Delisted/unknown ticker, or the free-tier rate limit kicked in --
        # either way, omit it rather than fabricate a price (same
        # not-available-over-fabricated principle as the Risk Agent).
        return None
    return QuoteResult(symbol=symbol, price=float(price_str))


@router.get("/quotes", response_model=list[QuoteResult])
async def get_quotes(symbols: str, current_user: User = Depends(get_current_user)) -> list[QuoteResult]:
    """Current price per symbol, for the holdings table's "Current cost"
    column. `symbols` is a comma-separated list so the frontend can fetch
    every holding's price in one request instead of one per row.
    """
    requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not requested:
        return []

    async with httpx.AsyncClient(timeout=10.0) as client:
        results = await asyncio.gather(*(_fetch_quote(client, symbol) for symbol in requested))

    return [quote for quote in results if quote is not None]
