from pydantic import BaseModel, Field


class HoldingCreate(BaseModel):
    symbol: str = Field(min_length=1, max_length=10)
    quantity: float = Field(gt=0)
    avg_cost: float = Field(ge=0)


class HoldingUpdate(HoldingCreate):
    pass


class HoldingResponse(BaseModel):
    id: int
    symbol: str
    quantity: float
    avg_cost: float

    model_config = {"from_attributes": True}

class SymbolSearchResult(BaseModel):
    symbol: str
    name: str


class QuoteResult(BaseModel):
    symbol: str
    price: float
