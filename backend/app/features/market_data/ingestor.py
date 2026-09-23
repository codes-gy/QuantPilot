"""장시간 상시 구동되는 실시간 시세 수집 프로세스 (Celery가 아닌 독립 asyncio 프로세스).

Celery worker는 짧은 작업(주문 실행 등)에 적합하고, 초 단위로 끊김없이 유지해야 하는
WebSocket 연결에는 맞지 않아 별도 프로세스로 분리했다 (docker-compose의 `ingestor` 서비스).

실행: python -m app.features.market_data.ingestor
"""

import asyncio

from app.core.logging import configure_logging, get_logger
from app.features.broker.base import AssetClass
from app.features.broker.factory import get_market_data_adapter
from app.features.market_data.factory import get_price_cache

logger = get_logger(__name__)

# TODO: 감시 종목 목록은 strategy 테이블에서 활성 전략이 참조하는 심볼을 동적으로 조회
WATCHED_KR_STOCKS = ["005930"]  # 삼성전자 등, placeholder
WATCHED_CRYPTO = ["KRW-BTC"]  # placeholder


async def _run_feed(asset_class: AssetClass, symbols: list[str]) -> None:
    adapter = get_market_data_adapter(asset_class)
    price_cache = get_price_cache()
    while True:
        try:
            async for tick in adapter.subscribe(symbols):
                await price_cache.cache_tick(asset_class, tick)
        except Exception:
            logger.exception("market data feed disconnected (%s), retrying in 3s", asset_class)
            await asyncio.sleep(3)  # 지수 백오프로 교체 권장


async def main() -> None:
    configure_logging()
    await asyncio.gather(
        _run_feed(AssetClass.KR_STOCK, WATCHED_KR_STOCKS),
        _run_feed(AssetClass.CRYPTO, WATCHED_CRYPTO),
    )


if __name__ == "__main__":
    asyncio.run(main())
