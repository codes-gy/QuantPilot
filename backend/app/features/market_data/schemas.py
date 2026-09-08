from pydantic import BaseModel


class PriceOut(BaseModel):
    symbol: str
    price: float
    timestamp: float


class CandleOut(BaseModel):
    symbol: str
    interval: str
    open: float
    high: float
    low: float
    close: float
    volume: float
