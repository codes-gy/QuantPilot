from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.strategy.models import Strategy
from app.features.strategy.schemas import StrategyCreate


async def create_strategy(db: AsyncSession, payload: StrategyCreate) -> Strategy:
    strategy = Strategy(**payload.model_dump())
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)
    return strategy


async def list_strategies(db: AsyncSession) -> list[Strategy]:
    result = await db.execute(select(Strategy))
    return list(result.scalars().all())
