"""trading 서비스/task가 의존하는 포트."""

from abc import ABC, abstractmethod

from app.features.trading.models import Order, Position


class OrderRepository(ABC):
    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[Order]: ...

    @abstractmethod
    async def get_by_client_order_id(self, client_order_id: str) -> Order | None:
        """Celery task 재시도 시 중복 주문 방지용 조회."""
        ...

    @abstractmethod
    async def add(self, order: Order) -> Order: ...

    @abstractmethod
    async def update(self, order: Order) -> Order: ...


class PositionRepository(ABC):
    @abstractmethod
    async def get_by_symbol(self, symbol: str) -> Position | None: ...

    @abstractmethod
    async def upsert(self, position: Position) -> Position: ...
