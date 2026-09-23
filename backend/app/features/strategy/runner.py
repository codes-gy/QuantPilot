"""활성 전략을 실시간 시세에 반응시켜 평가하는 상시 구동 프로세스.

Redis 시세 pub/sub을 구독하다가 틱이 들어올 때마다 해당 심볼을 감시하는 전략만 골라
evaluate 하는 이벤트 기반 구조 — polling 대신 이 방식을 쓰는 이유는 초 단위 미만의
반응 지연을 없애기 위함. 신호가 발생하면 risk.guard를 통과한 뒤 trading.tasks의
Celery task로 실행을 위임한다 (주문 자체는 재시도가 필요한 부수효과라 Celery가 적합).

실행: python -m app.features.strategy.runner
"""

import asyncio
import uuid

from app.core.logging import configure_logging, get_logger
from app.features.broker.base import AssetClass
from app.features.market_data.factory import get_price_cache
from app.features.notification.factory import get_notification_service
from app.features.risk.guard import RiskGuard
from app.features.risk.redis_repository import RedisKillSwitchRepository
from app.features.strategy.engine import MarketSnapshot, Signal, evaluate_entry, evaluate_exit
from app.features.trading.tasks import submit_order_task

logger = get_logger(__name__)


async def run() -> None:
    configure_logging()
    risk_guard = RiskGuard(
        kill_switch=RedisKillSwitchRepository(),
        notifier=get_notification_service(),
    )
    price_cache = get_price_cache()

    # TODO: StrategyRepository(SqlAlchemyStrategyRepository).list_active()로 활성 전략을
    #       동적으로 로드해 심볼을 구독 (5단계 범위 — 러너의 전략 로딩 로직 자체는 별도 작업)
    watched_symbols: list[str] = []

    async for data in price_cache.subscribe(AssetClass.KR_STOCK, watched_symbols):
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
            # TODO: quantity는 전략의 max_position_size/포지션 사이징 규칙에서 결정해야 함
            #       (지금은 5단계 전략 매핑 로직 미구현 상태라 placeholder)
            submit_order_task.delay(
                client_order_id=str(uuid.uuid4()),
                symbol=snapshot.symbol,
                side=signal.value,
                quantity=1.0,
            )


if __name__ == "__main__":
    asyncio.run(run())
