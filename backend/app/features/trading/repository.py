"""OrderRepository / PositionRepository 포트의 SQLAlchemy 구현체."""

from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.trading.models import Order, OrderStatus, Position
from app.features.trading.ports import OrderRepository, PositionRepository

_NON_FINAL_STATUSES = (OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED)
# 브로커 전송 전에 실패해 PENDING으로 남은 주문이 해당 종목 매매를 영원히 막지 않도록,
# 브로커 주문번호가 없는 PENDING 주문은 이 시간 안에 생성된 것만 "진행 중"으로 본다.
_STALE_PENDING_AFTER = timedelta(minutes=10)


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

    async def list_pending(self) -> list[Order]:
        result = await self._db.execute(
            select(Order)
            .where(Order.status.in_([s.value for s in _NON_FINAL_STATUSES]))
            .where(Order.broker_order_id.is_not(None))  # 브로커에 아직 안 나간 주문은 폴링 대상 아님
            .order_by(Order.created_at.asc())
        )
        return list(result.scalars().all())

    async def has_open_order(self, symbol: str) -> bool:
        """해당 종목에 아직 최종 상태가 아닌 주문이 있는지. 전략 러너가 같은 신호로
        주문을 중복 제출하지 않도록 신규 주문 전에 확인한다.
        """
        stale_before = datetime.utcnow() - _STALE_PENDING_AFTER
        result = await self._db.execute(
            select(Order.id)
            .where(Order.symbol == symbol)
            .where(Order.status.in_([s.value for s in _NON_FINAL_STATUSES]))
            .where(
                or_(
                    Order.broker_order_id.is_not(None),
                    and_(Order.status == OrderStatus.PENDING.value, Order.created_at >= stale_before),
                )
            )
            .limit(1)
        )
        return result.first() is not None

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

    async def list_all(self) -> list[Position]:
        # 잔고 0인 포지션(전량 매도 후 남은 레코드)은 대시보드에서 의미가 없으므로 제외한다.
        result = await self._db.execute(
            select(Position).where(Position.quantity != 0).order_by(Position.symbol.asc())
        )
        return list(result.scalars().all())
