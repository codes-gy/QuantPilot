"""RiskGuard가 의존하는 포트.

kill switch가 지금은 Redis에 저장되지만, RiskGuard 자체는 그 사실을 몰라야 한다 —
저장소를 바꾸거나(예: 감사 로그 겸용 DB) 테스트에서 in-memory 구현으로 교체해도
guard.py는 수정할 필요가 없다.
"""

from abc import ABC, abstractmethod


class KillSwitchRepository(ABC):
    @abstractmethod
    async def is_engaged(self) -> bool: ...

    @abstractmethod
    async def engage(self) -> None: ...

    @abstractmethod
    async def release(self) -> None: ...
