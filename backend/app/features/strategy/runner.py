"""활성 전략을 실시간 시세에 반응시켜 평가하는 상시 구동 프로세스.

Redis 시세 pub/sub을 구독하다가 틱이 들어올 때마다 해당 심볼을 감시하는 전략만 골라
evaluate 하는 이벤트 기반 구조 — polling 대신 이 방식을 쓰는 이유는 초 단위 미만의
반응 지연을 없애기 위함. 신호가 발생하면 risk.guard를 통과한 뒤 trading.tasks의
Celery task로 실행을 위임한다 (주문 자체는 재시도가 필요한 부수효과라 Celery가 적합).

활성 전략 목록은 REFRESH_INTERVAL_SECONDS마다 DB에서 다시 읽어 구독 심볼을 갱신한다
(전략을 새로 추가/일시정지해도 재배포 없이 다음 주기에 반영됨). Redis pub/sub 자체는
런타임에 구독을 추가/해제할 수 있지만, 여기서는 구현 단순성을 위해 매 주기마다
구독을 통째로 재시작하는 방식을 쓴다 — 개인용 프로젝트 규모(전략 수가 적음)에서는
재구독 비용이 무시할 만하다.

실행: python -m app.features.strategy.runner
"""

import asyncio
import time
import uuid
from collections import defaultdict

from app.core.config import get_settings
from app.core.exceptions import RiskLimitExceededError
from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.features.broker.base import AssetClass
from app.features.market_data.factory import get_price_cache
from app.features.notification.factory import get_notification_service
from app.features.risk.guard import RiskGuard
from app.features.risk.redis_repository import RedisDailyPnlRepository, RedisKillSwitchRepository
from app.features.strategy.engine import MarketSnapshot, Signal, evaluate_entry, evaluate_exit
from app.features.strategy.models import Strategy
from app.features.strategy.repository import SqlAlchemyStrategyRepository
from app.features.trading.repository import SqlAlchemyPositionRepository
from app.features.trading.tasks import submit_order_task

logger = get_logger(__name__)

REFRESH_INTERVAL_SECONDS = 30
MAX_PRICE_HISTORY = 200


async def _load_active_strategies() -> list[Strategy]:
    async with AsyncSessionLocal() as db:
        return await SqlAlchemyStrategyRepository(db).list_active()


async def _current_position_qty_and_entry(symbol: str) -> tuple[float, float] | None:
    """(수량, 평균진입가) — 포지션이 없으면 None."""
    async with AsyncSessionLocal() as db:
        position = await SqlAlchemyPositionRepository(db).get_by_symbol(symbol)
        if position is None or position.quantity <= 0:
            return None
        return position.quantity, position.avg_entry_price


async def _evaluate_strategy(
    strategy: Strategy, snapshot: MarketSnapshot, risk_guard: RiskGuard
) -> None:
    position = await _current_position_qty_and_entry(strategy.symbol)
    signal = Signal.HOLD

    # 1. 보유 포지션이 있으면 손절 조건부터 확인 — exit_rule과 무관하게 항상 강제 청산.
    if position is not None:
        qty, entry_price = position
        try:
            await risk_guard.check_stop_loss(
                strategy.symbol, entry_price, snapshot.price, strategy.stop_loss_pct
            )
        except RiskLimitExceededError as exc:
            logger.warning("stop-loss triggered: %s", exc)
            signal = Signal.SELL

    # 2. 손절이 아니면 전략의 exit_rule로 일반 청산 신호 평가.
    if signal is Signal.HOLD and position is not None and strategy.exit_rule:
        signal = evaluate_exit(strategy.exit_rule, snapshot)

    # 3. 청산 신호가 없고, 기존 포지션도 없을 때만 신규 진입(entry_rule) 평가.
    #    (포지션이 이미 있는데 추가 매수하는 피라미딩은 이 엔진에서 아직 지원하지 않음)
    if signal is Signal.HOLD and position is None and strategy.entry_rule:
        candidate = evaluate_entry(strategy.entry_rule, snapshot)
        if candidate is Signal.BUY:
            # TODO: 지금은 max_position_size 전량을 한 번에 매수하는 단순 사이징이다.
            #       분할 매수/자금 배분 등 정교한 사이징 규칙은 이후 개선 대상.
            try:
                await risk_guard.check_position_size(
                    strategy.max_position_size, strategy.max_position_size
                )
            except RiskLimitExceededError as exc:
                logger.info("entry blocked by position size limit: %s", exc)
            else:
                signal = candidate

    if signal is Signal.HOLD:
        return

    quantity = position[0] if signal is Signal.SELL and position is not None else strategy.max_position_size
    submit_order_task.delay(
        client_order_id=str(uuid.uuid4()),
        symbol=strategy.symbol,
        side=signal.value,
        quantity=quantity,
        asset_class=strategy.asset_class,
        strategy_id=strategy.id,
    )


async def run() -> None:
    configure_logging()
    settings = get_settings()
    risk_guard = RiskGuard(
        kill_switch=RedisKillSwitchRepository(),
        notifier=get_notification_service(),
        daily_pnl=RedisDailyPnlRepository(),
        daily_loss_limit_krw=settings.daily_loss_limit_krw,
    )
    price_cache = get_price_cache()
    price_history: dict[str, list[float]] = defaultdict(list)

    while True:
        strategies = await _load_active_strategies()
        symbol_strategies: dict[str, list[Strategy]] = defaultdict(list)
        for strategy in strategies:
            if strategy.asset_class == AssetClass.KR_STOCK.value:
                symbol_strategies[strategy.symbol].append(strategy)
        watched_symbols = list(symbol_strategies.keys())

        if not watched_symbols:
            logger.info(
                "no active KR_STOCK strategies; rechecking in %ss", REFRESH_INTERVAL_SECONDS
            )
            await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
            continue

        logger.info("subscribing to %d symbol(s): %s", len(watched_symbols), watched_symbols)
        subscription = price_cache.subscribe(AssetClass.KR_STOCK, watched_symbols)
        cycle_deadline = time.monotonic() + REFRESH_INTERVAL_SECONDS

        while time.monotonic() < cycle_deadline:
            try:
                remaining = max(cycle_deadline - time.monotonic(), 0.1)
                data = await asyncio.wait_for(subscription.__anext__(), timeout=remaining)
            except (TimeoutError, StopAsyncIteration):
                break

            symbol = data["symbol"]
            history = price_history[symbol]
            history.append(data["price"])
            if len(history) > MAX_PRICE_HISTORY:
                del history[: len(history) - MAX_PRICE_HISTORY]

            snapshot = MarketSnapshot(symbol=symbol, price=data["price"], price_history=list(history))

            if not await risk_guard.is_trading_allowed():
                continue

            for strategy in symbol_strategies.get(symbol, []):
                await _evaluate_strategy(strategy, snapshot, risk_guard)

        await subscription.aclose()


if __name__ == "__main__":
    asyncio.run(run())
