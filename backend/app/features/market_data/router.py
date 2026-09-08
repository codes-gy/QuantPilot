from fastapi import APIRouter, HTTPException

from app.features.broker.base import AssetClass
from app.features.market_data.cache import get_latest_price, now_ts
from app.features.market_data.schemas import PriceOut

router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/{asset_class}/{symbol}/price", response_model=PriceOut)
async def get_price(asset_class: AssetClass, symbol: str) -> PriceOut:
    price = await get_latest_price(asset_class, symbol)
    if price is None:
        raise HTTPException(status_code=404, detail="no cached price for symbol")
    return PriceOut(symbol=symbol, price=price, timestamp=now_ts())
