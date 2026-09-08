"""활성 전략을 실시간 시세에 반응시켜 평가하는 상시 구동 프로세스.

Redis 시세 pub/sub을 구독하다가 틱이 들어올 때마다 해당 심볼을 감시하는 전략만 골라
evaluate 하는 이벤트 기반 구조 — polling 대신 이 방식을 쓰는 이유는 초 단위 미만의
반응 지연을 없애기 위함. 신호가 발생하면 risk.guard를 통과한 뒤 trading.tasks의
Celery task로 실행을 위임한다 (주문 자체는 재시도가 필요한 부수효과라 Celery가 적합).

실행: python -m app.features.strategy.runner
"""

import asyncio
import json

from app.core.logging import configure_logging, get_logger
from app.features.broker.base import AssetClass
from app.features.market_data.cache import subscribe_price_channel
from app.features.risk.guard import RiskGuard
from app.features.strategy.engine import MarketSnapshot, Signal, evaluate_entry, evaluate_exit
from app.features.trading.tasks import submit_order_task

logger = get_logger(__name__)


async def run() -> None:
    configure_logging()
    risk_guard = RiskGuard()

    # TODO: DB에서 활성(status=active) 전략 목록/심볼을 로드해 동적으로 구독
    watched_symbols: list[str] = []
    pubsub = await subscribe_price_channel(AssetClass.KR_STOCK, watched_symbols)

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = json.loads(message["data"])

        # TODO: 심볼에 매핑된 전략들을 순회하며 MarketSnapshot 구성 후 평가
        snapshot = MarketSnapshot(symbol="", price=data["price"], price_history=[])
        strategy_entry_rule: dict = {}
        strategy_exit_rule: dict = {}

        if not await risk_guard.is_trading_allowed():
            continue

        signal = evaluate_entry(strategy_entry_rule, snapshot) if strategy_entry_rule else Signal.HOLD
        if signal is Signal.HOLD:
            signal = evaluate_exit(strategy_exit_rule, snapshot) if strategy_exit_rule else Signal.HOLD

        if signal is not Signal.HOLD:
            submit_order_task.delay(symbol=snapshot.symbol, side=signal.value)


if __name__ == "__main__":
    asyncio.run(run())
