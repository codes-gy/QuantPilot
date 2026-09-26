"""features 테스트 전반에서 재사용하는 인메모리 fake 구현들.

RiskGuard/OrderExecutionFacade는 포트(ABC)에만 의존하도록 설계되어 있어서,
실제 Redis/DB 없이도 이 fake들로 완전히 테스트할 수 있다.
"""

import pytest

from app.features.risk.ports import DailyPnlRepository, KillSwitchRepository


class InMemoryKillSwitch(KillSwitchRepository):
    def __init__(self) -> None:
        self._engaged = False

    async def is_engaged(self) -> bool:
        return self._engaged

    async def engage(self) -> None:
        self._engaged = True

    async def release(self) -> None:
        self._engaged = False


class InMemoryDailyPnl(DailyPnlRepository):
    def __init__(self) -> None:
        self._total = 0.0

    async def record_realized_pnl(self, amount: float) -> float:
        self._total += amount
        return self._total

    async def get_today_realized_pnl(self) -> float:
        return self._total


class RecordingNotifier:
    """NotificationService 대신 주입해, 어떤 이벤트가 몇 번 발송됐는지 검증한다."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    async def notify(self, event_type: str, message: str) -> None:
        self.events.append((event_type, message))


@pytest.fixture
def kill_switch() -> InMemoryKillSwitch:
    return InMemoryKillSwitch()


@pytest.fixture
def daily_pnl() -> InMemoryDailyPnl:
    return InMemoryDailyPnl()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()
