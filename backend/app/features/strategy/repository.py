"""StrategyRepository 포트의 SQLAlchemy 구현체."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.strategy.models import Strategy, StrategyStatus
from app.features.strategy.ports import StrategyRepository


class SqlAlchemyStrategyRepository(StrategyRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def add(self, strategy: Strategy) -> Strategy:
        self._db.add(strategy)
        await self._db.commit()
        await self._db.refresh(strategy)
        return strategy

    async def list_all(self) -> list[Strategy]:
        result = await self._db.execute(select(Strategy))
        return list(result.scalars().all())

    async def list_active(self) -> list[Strategy]:
        result = await self._db.execute(
            select(Strategy).where(Strategy.status == StrategyStatus.ACTIVE)
        )
        return list(result.scalars().all())
