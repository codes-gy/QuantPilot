"""RiskGuard가 의존하는 포트.

kill switch가 지금은 Redis에 저장되지만, RiskGuard 자체는 그 사실을 몰라야 한다 —
저장소를 바꾸거나(예: 감사 로그 겸용 DB) 테스트에서 in-memory 구현으로 교체해도
guard.py는 수정할 필요가 없다.
"""

from abc import ABC, abstractmethod

from app.features.risk.models import KillSwitchAuditLog


class KillSwitchRepository(ABC):
    @abstractmethod
    async def is_engaged(self) -> bool: ...

    @abstractmethod
    async def engage(self) -> None: ...

    @abstractmethod
    async def release(self) -> None: ...


class DailyPnlRepository(ABC):
    """일일 실현손익 누적 — 전략별 stop_loss_pct와 별개로, 계좌 전체의 하루 손실 한도를
    감시하기 위한 저장소. 날짜가 바뀌면 자동으로 0부터 다시 시작해야 한다.
    """

    @abstractmethod
    async def record_realized_pnl(self, amount: float) -> float:
        """오늘 누적 실현손익에 amount(음수면 손실)를 더하고, 갱신된 누적값을 반환."""
        ...

    @abstractmethod
    async def get_today_realized_pnl(self) -> float: ...


class KillSwitchAuditLogRepository(ABC):
    """kill switch 발동 사유를 영구 기록하는 저장소 (kill switch on/off 상태 자체는
    KillSwitchRepository/Redis가 담당하고, 이 저장소는 감사 추적 전용이다).
    """

    @abstractmethod
    async def record(self, reason: str) -> None: ...

    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[KillSwitchAuditLog]: ...
