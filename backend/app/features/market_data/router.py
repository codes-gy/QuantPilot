from fastapi import APIRouter, Depends, HTTPException, Query

from app.core.deps import get_current_user
from app.core.exceptions import BrokerAPIError, SymbolNotFoundError
from app.features.broker.base import AssetClass
from app.features.broker.factory import get_broker_adapter
from app.features.market_data.factory import get_price_cache
from app.features.market_data.ports import PriceCachePort
from app.features.market_data.schemas import PriceOut, QuoteOut, SymbolOut
from app.features.market_data.symbols import SymbolDirectory, get_symbol_directory
from app.features.market_data.utils import now_ts

router = APIRouter(prefix="/market-data", tags=["market-data"], dependencies=[Depends(get_current_user)])


@router.get("/{asset_class}/symbols", response_model=list[SymbolOut])
async def search_symbols(
    asset_class: AssetClass,
    q: str = Query(min_length=1, max_length=50, description="종목명 또는 종목코드 일부"),
    limit: int = Query(default=20, ge=1, le=50),
    directory: SymbolDirectory = Depends(get_symbol_directory),
) -> list[SymbolOut]:
    """종목명/코드로 검색한다 (주식: KIS 종목 마스터, 코인: Upbit 원화 마켓)."""
    try:
        results = await directory.search(asset_class, q, limit)
    except BrokerAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return [SymbolOut(symbol=s.symbol, name=s.name, market=s.market) for s in results]


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
