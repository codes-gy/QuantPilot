from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import get_current_user
from app.core.exceptions import BrokerAPIError, SymbolNotFoundError
from app.features.broker.base import AssetClass
from app.features.broker.factory import get_broker_adapter
from app.features.market_data.factory import get_price_cache
from app.features.market_data.ports import PriceCachePort
from app.features.market_data.schemas import PriceOut, QuoteOut
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


@router.get("/{asset_class}/{symbol}/quote", response_model=QuoteOut)
async def get_quote(asset_class: AssetClass, symbol: str) -> QuoteOut:
    """증권사/거래소에 직접 현재가와 종목명을 조회한다. 위의 /price는 켜진 전략의 종목만
    들어 있는 시세 캐시를 읽으므로, 전략을 등록하기 전에는 이 엔드포인트를 쓴다.
    """
    symbol = symbol.upper()
    try:
        quote = await get_broker_adapter(asset_class).get_quote(symbol)
    except SymbolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except BrokerAPIError as exc:
        raise HTTPException(status_code=502, detail=f"시세 조회 실패: {exc}") from exc
    return QuoteOut(symbol=quote.symbol, name=quote.name, price=quote.price, change_rate=quote.change_rate)
