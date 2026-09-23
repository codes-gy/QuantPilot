"""장시간 상시 구동되는 실시간 시세 수집 프로세스 (Celery가 아닌 독립 asyncio 프로세스).

Celery worker는 짧은 작업(주문 실행 등)에 적합하고, 초 단위로 끊김없이 유지해야 하는
WebSocket 연결에는 맞지 않아 별도 프로세스로 분리했다 (docker-compose의 `ingestor` 서비스).

감시 종목은 strategy 테이블의 활성(status=active) 전략이 참조하는 심볼을
REFRESH_INTERVAL_SECONDS마다 다시 조회해 동적으로 구독한다 — strategy/runner.py와
동일한 패턴(매 주기마다 구독을 통째로 재시작)을 쓴다.

실행: python -m app.features.market_data.ingestor
"""

import asyncio
import time
from collections import defaultdict

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.features.broker.base import AssetClass
from app.features.broker.factory import get_market_data_adapter
from app.features.market_data.factory import get_price_cache
from app.features.strategy.repository import SqlAlchemyStrategyRepository

logger = get_logger(__name__)

REFRESH_INTERVAL_SECONDS = 30


async def _load_watched_symbols() -> dict[AssetClass, list[str]]:
    async with AsyncSessionLocal() as db:
        strategies = await SqlAlchemyStrategyRepository(db).list_active()

    watched: dict[AssetClass, set[str]] = defaultdict(set)
    for strategy in strategies:
        try:
            asset_class = AssetClass(strategy.asset_class)
        except ValueError:
            logger.warning("unknown asset_class in strategy %s: %s", strategy.id, strategy.asset_class)
            continue
        watched[asset_class].add(strategy.symbol)

    return {asset_class: sorted(symbols) for asset_class, symbols in watched.items()}


async def _run_feed(asset_class: AssetClass) -> None:
    adapter = get_market_data_adapter(asset_class)
    price_cache = get_price_cache()

    while True:
        watched = await _load_watched_symbols()
        symbols = watched.get(asset_class, [])

        if not symbols:
            logger.info(
                "no active strategies for %s; rechecking in %ss", asset_class, REFRESH_INTERVAL_SECONDS
            )
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            continue

        logger.info("subscribing %s to %d symbol(s): %s", asset_class, len(symbols), symbols)
        try:
            subscription = adapter.subscribe(symbols)
            cycle_deadline = time.monotonic() + REFRESH_INTERVAL_SECONDS

            while time.monotonic() < cycle_deadline:
                remaining = max(cycle_deadline - time.monotonic(), 0.1)
                try:
                    tick = await asyncio.wait_for(subscription.__anext__(), timeout=remaining)
                except (TimeoutError, StopAsyncIteration):
                    break
                await price_cache.cache_tick(asset_class, tick)

            await subscription.aclose()
        except Exception:
            logger.exception("market data feed disconnected (%s), retrying in 3s", asset_class)
            await asyncio.sleep(3)  # 지수 백오프로 교체 권장


async def main() -> None:
    configure_logging()
    await asyncio.gather(
        _run_feed(AssetClass.KR_STOCK),
        _run_feed(AssetClass.CRYPTO),
    )


if __name__ == "__main__":
    asyncio.run(main())
