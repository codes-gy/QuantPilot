"""전략 서비스/러너가 의존하는 포트."""

from abc import ABC, abstractmethod

from app.features.strategy.models import Strategy


class StrategyRepository(ABC):
    @abstractmethod
    async def add(self, strategy: Strategy) -> Strategy: ...

    @abstractmethod
    async def list_all(self) -> list[Strategy]: ...

    @abstractmethod
    async def list_active(self) -> list[Strategy]:
        """strategy-runner가 구독할 심볼을 정하기 위해 status=active인 전략만 조회."""
        ...
