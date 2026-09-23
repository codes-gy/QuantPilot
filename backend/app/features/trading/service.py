"""주문 조회 애플리케이션 서비스 — OrderRepository 포트에만 의존한다."""

from app.features.trading.models import Order
from app.features.trading.ports import OrderRepository


class TradingService:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def list_orders(self, limit: int = 50) -> list[Order]:
        return await self._orders.list_recent(limit)
