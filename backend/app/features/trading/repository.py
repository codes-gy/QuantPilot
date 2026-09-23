"""OrderRepository / PositionRepository 포트의 SQLAlchemy 구현체."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.trading.models import Order, Position
from app.features.trading.ports import OrderRepository, PositionRepository


class SqlAlchemyOrderRepository(OrderRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_recent(self, limit: int = 50) -> list[Order]:
        result = await self._db.execute(
            select(Order).order_by(Order.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_client_order_id(self, client_order_id: str) -> Order | None:
        result = await self._db.execute(
            select(Order).where(Order.client_order_id == client_order_id)
        )
        return result.scalar_one_or_none()

    async def add(self, order: Order) -> Order:
        self._db.add(order)
        await self._db.commit()
        await self._db.refresh(order)
        return order

    async def update(self, order: Order) -> Order:
        await self._db.commit()
        await self._db.refresh(order)
        return order


class SqlAlchemyPositionRepository(PositionRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_symbol(self, symbol: str) -> Position | None:
        result = await self._db.execute(select(Position).where(Position.symbol == symbol))
        return result.scalar_one_or_none()

    async def upsert(self, position: Position) -> Position:
        existing = await self.get_by_symbol(position.symbol)
        if existing is None:
            self._db.add(position)
        await self._db.commit()
        await self._db.refresh(existing or position)
        return existing or position
