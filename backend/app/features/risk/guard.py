"""모든 주문 제출 경로가 반드시 거쳐야 하는 마지막 방어선.

trading/tasks.py의 submit_order_task는 KIS/Upbit 어댑터를 호출하기 *직전에* 반드시
RiskGuard.check(...)를 호출해야 한다. 여기서 막힌 주문은 조용히 버리지 않고
KillSwitchEngagedError/RiskLimitExceededError를 던져 감사 로그에 남긴다.
"""

from app.core.exceptions import KillSwitchEngagedError, RiskLimitExceededError
from app.db.redis import get_redis

_KILL_SWITCH_KEY = "kill_switch:global"


class RiskGuard:
    async def is_trading_allowed(self) -> bool:
        redis = get_redis()
        value = await redis.get(_KILL_SWITCH_KEY)
        return value != "true"

    async def engage_kill_switch(self, reason: str) -> None:
        """비상 정지. API/앱에서 버튼 한 번으로 즉시 호출 — 모든 신규 주문을 차단한다."""
        redis = get_redis()
        await redis.set(_KILL_SWITCH_KEY, "true")
        # TODO: notification 채널로 즉시 알림 발송, 사유 감사 로그 기록(reason)

    async def release_kill_switch(self) -> None:
        redis = get_redis()
        await redis.delete(_KILL_SWITCH_KEY)

    async def check_stop_loss(self, symbol: str, entry_price: float, current_price: float, stop_loss_pct: float) -> None:
        loss_pct = (entry_price - current_price) / entry_price
        if loss_pct >= stop_loss_pct:
            raise RiskLimitExceededError(
                f"{symbol} stop-loss triggered: -{loss_pct:.2%} >= -{stop_loss_pct:.2%}"
            )

    async def check_position_size(self, requested_qty: float, max_position_size: float) -> None:
        if requested_qty > max_position_size:
            raise RiskLimitExceededError(
                f"requested quantity {requested_qty} exceeds max position size {max_position_size}"
            )

    async def assert_can_trade(self) -> None:
        if not await self.is_trading_allowed():
            raise KillSwitchEngagedError("kill switch is engaged; new orders are blocked")
