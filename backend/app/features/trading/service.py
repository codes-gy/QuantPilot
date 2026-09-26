"""주문/포지션 조회 애플리케이션 서비스 — OrderRepository/PositionRepository 포트에만 의존한다."""

from app.features.trading.models import Order, Position
from app.features.trading.ports import OrderRepository, PositionRepository


class TradingService:
    def __init__(self, orders: OrderRepository, positions: PositionRepository) -> None:
        self._orders = orders
        self._positions = positions

    async def list_orders(self, limit: int = 50) -> list[Order]:
        return await self._orders.list_recent(limit)

    async def list_positions(self) -> list[Position]:
        return await self._positions.list_all()
