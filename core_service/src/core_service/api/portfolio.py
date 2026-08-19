from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from core_service.api.deps import get_current_user
from core_service.db.models import Holding, Portfolio, User
from core_service.db.session import get_db
from core_service.schemas.portfolio import HoldingCreate, HoldingResponse, HoldingUpdate

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
