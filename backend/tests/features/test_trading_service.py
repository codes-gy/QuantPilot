"""TradingService.list_positions() 테스트 (GET /positions가 이 서비스를 사용한다)."""

import pytest

from app.features.trading.models import Position
from app.features.trading.ports import OrderRepository, PositionRepository
from app.features.trading.service import TradingService


class _UnusedOrderRepository(OrderRepository):
    """list_positions()만 테스트하므로 주문 관련 메서드는 호출될 일이 없다."""

    async def list_recent(self, limit: int = 50):
        raise NotImplementedError

    async def get_by_client_order_id(self, client_order_id: str):
        raise NotImplementedError

    async def list_pending(self):
        raise NotImplementedError

    async def add(self, order):
        raise NotImplementedError

    async def update(self, order):
        raise NotImplementedError


class InMemoryPositionRepository(PositionRepository):
    def __init__(self, positions: list[Position]) -> None:
        self._positions = positions

    async def get_by_symbol(self, symbol: str) -> Position | None:
        return next((p for p in self._positions if p.symbol == symbol), None)

    async def upsert(self, position: Position) -> Position:
        raise NotImplementedError

    async def list_all(self) -> list[Position]:
        return [p for p in self._positions if p.quantity != 0]


@pytest.fixture
def unused_orders() -> _UnusedOrderRepository:
    return _UnusedOrderRepository()


async def test_list_positions_returns_all_nonzero_positions(unused_orders):
    positions = [
        Position(asset_class="kr_stock", symbol="005930", quantity=10, avg_entry_price=70_000),
        Position(asset_class="kr_stock", symbol="000660", quantity=5, avg_entry_price=120_000),
    ]
    service = TradingService(orders=unused_orders, positions=InMemoryPositionRepository(positions))

    result = await service.list_positions()

    assert {p.symbol for p in result} == {"005930", "000660"}


async def test_list_positions_excludes_fully_closed_positions(unused_orders):
    """전량 매도해서 quantity가 0이 된 포지션 레코드는 대시보드에 보일 필요가 없다."""
    positions = [
        Position(asset_class="kr_stock", symbol="005930", quantity=10, avg_entry_price=70_000),
        Position(asset_class="kr_stock", symbol="000660", quantity=0, avg_entry_price=120_000),
    ]
    service = TradingService(orders=unused_orders, positions=InMemoryPositionRepository(positions))

    result = await service.list_positions()

    assert [p.symbol for p in result] == ["005930"]
