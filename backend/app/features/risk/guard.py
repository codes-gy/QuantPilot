"""모든 주문 제출 경로가 반드시 거쳐야 하는 마지막 방어선.

trading/tasks.py의 submit_order_task는 KIS/Upbit 어댑터를 호출하기 *직전에* 반드시
RiskGuard.check(...)를 호출해야 한다. 여기서 막힌 주문은 조용히 버리지 않고
KillSwitchEngagedError/RiskLimitExceededError를 던져 감사 로그에 남긴다.

kill switch 저장소(KillSwitchRepository)와 알림(NotificationService)은 모두 포트로
주입받는다 — 이 클래스는 Redis도, WebSocket도 알지 못한다.
"""

from app.core.exceptions import KillSwitchEngagedError, RiskLimitExceededError
from app.features.notification.service import NotificationService
from app.features.risk.ports import KillSwitchRepository


class RiskGuard:
    def __init__(
        self,
        kill_switch: KillSwitchRepository,
        notifier: NotificationService | None = None,
    ) -> None:
        self._kill_switch = kill_switch
        self._notifier = notifier

    async def is_trading_allowed(self) -> bool:
        return not await self._kill_switch.is_engaged()

    async def engage_kill_switch(self, reason: str) -> None:
        """비상 정지. API/앱에서 버튼 한 번으로 즉시 호출 — 모든 신규 주문을 차단한다."""
        await self._kill_switch.engage()
        if self._notifier is not None:
            await self._notifier.notify("kill_switch_engaged", reason)
        # TODO: 사유(reason) 감사 로그를 DB에 영구 기록 (지금은 notification으로만 전파됨)

    async def release_kill_switch(self) -> None:
        await self._kill_switch.release()

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
