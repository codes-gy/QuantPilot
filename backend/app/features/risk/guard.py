"""모든 주문 제출 경로가 반드시 거쳐야 하는 마지막 방어선.

trading/tasks.py의 submit_order_task는 KIS/Upbit 어댑터를 호출하기 *직전에* 반드시
RiskGuard.check(...)를 호출해야 한다. 여기서 막힌 주문은 조용히 버리지 않고
KillSwitchEngagedError/RiskLimitExceededError를 던져 감사 로그에 남긴다.

kill switch 저장소(KillSwitchRepository), 일일 손익 저장소(DailyPnlRepository), 알림
(NotificationService)은 모두 포트로 주입받는다 — 이 클래스는 Redis도, WebSocket도
알지 못한다.
"""

from app.core.exceptions import KillSwitchEngagedError, RiskLimitExceededError
from app.core.logging import get_logger
from app.features.notification.service import NotificationService
from app.features.risk.ports import DailyPnlRepository, KillSwitchAuditLogRepository, KillSwitchRepository

logger = get_logger(__name__)


class RiskGuard:
    def __init__(
        self,
        kill_switch: KillSwitchRepository,
        notifier: NotificationService | None = None,
        daily_pnl: DailyPnlRepository | None = None,
        daily_loss_limit_krw: float | None = None,
        audit_log: KillSwitchAuditLogRepository | None = None,
    ) -> None:
        self._kill_switch = kill_switch
        self._notifier = notifier
        self._daily_pnl = daily_pnl
        self._daily_loss_limit_krw = daily_loss_limit_krw
        self._audit_log = audit_log

    async def is_trading_allowed(self) -> bool:
        return not await self._kill_switch.is_engaged()

    async def engage_kill_switch(self, reason: str) -> None:
        """비상 정지. API/앱에서 버튼 한 번으로 즉시 호출 — 모든 신규 주문을 차단한다."""
        await self._kill_switch.engage()
        if self._notifier is not None:
            await self._notifier.notify("kill_switch_engaged", reason)
        if self._audit_log is not None:
            await self._audit_log.record(reason)

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

    async def record_fill_pnl(self, realized_pnl: float) -> None:
        """매도 체결로 확정된 손익을 오늘 누적치에 반영하고, 일일 손실 한도를 넘었으면
        kill switch를 자동 발동한다. 전략별 stop_loss_pct(개별 포지션 기준)와는 별개로,
        계좌 전체 기준의 상위 서킷브레이커 역할을 한다.
        """
        if self._daily_pnl is None:
            return

        total = await self._daily_pnl.record_realized_pnl(realized_pnl)

        if self._daily_loss_limit_krw is None:
            return
        if total > -self._daily_loss_limit_krw:
            return
        if await self._kill_switch.is_engaged():
            return  # 이미 발동됨 — 중복 알림 방지

        reason = (
            f"일일 손실 한도 초과: 실현손익 {total:,.0f}원 "
            f"(한도 -{self._daily_loss_limit_krw:,.0f}원)"
        )
        logger.warning(reason)
        await self.engage_kill_switch(reason)

    async def get_today_realized_pnl(self) -> float:
        if self._daily_pnl is None:
            return 0.0
        return await self._daily_pnl.get_today_realized_pnl()

    async def assert_can_trade(self) -> None:
        if not await self.is_trading_allowed():
            raise KillSwitchEngagedError("kill switch is engaged; new orders are blocked")
