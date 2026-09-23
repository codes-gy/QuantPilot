from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.features.broker.base import AssetClass
from app.features.market_data.factory import get_price_cache
from app.features.market_data.ports import PriceCachePort
from app.features.market_data.schemas import PriceOut
from app.features.market_data.utils import now_ts

router = APIRouter(prefix="/market-data", tags=["market-data"], dependencies=[Depends(get_current_user)])


@router.get("/{asset_class}/{symbol}/price", response_model=PriceOut)
async def get_price(
    asset_class: AssetClass, symbol: str, cache: PriceCachePort = Depends(get_price_cache)
) -> PriceOut:
    price = await cache.get_latest_price(asset_class, symbol)
    if price is None:
        raise HTTPException(status_code=404, detail="no cached price for symbol")
    return PriceOut(symbol=symbol, price=price, timestamp=now_ts())
