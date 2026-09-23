"""전략 애플리케이션 서비스 — StrategyRepository 포트에만 의존한다."""

from app.features.strategy.models import Strategy
from app.features.strategy.ports import StrategyRepository
from app.features.strategy.schemas import StrategyCreate


class StrategyService:
    def __init__(self, strategies: StrategyRepository) -> None:
        self._strategies = strategies

    async def create_strategy(self, payload: StrategyCreate) -> Strategy:
        strategy = Strategy(**payload.model_dump())
        return await self._strategies.add(strategy)

    async def list_strategies(self) -> list[Strategy]:
        return await self._strategies.list_all()
