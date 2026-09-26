"""OrderExecutionFacade(신호 -> 리스크 재확인 -> 주문 -> 포지션 반영) 테스트.

이 파사드가 실제 돈이 오가는 유일한 진입점인데도 기존에 전혀 테스트되어
있지 않아서 새로 작성했다. 특히 멱등성(재시도 시 중복 주문 방지)과
kill switch가 브로커 호출 *전에* 반드시 걸러지는지를 중점적으로 검증한다.
"""

import pytest

from app.core.exceptions import KillSwitchEngagedError
from app.features.broker.base import AssetClass, Balance, BrokerAdapter, OrderRequest, OrderResult
from app.features.risk.guard import RiskGuard
from app.features.trading.facade import OrderExecutionFacade
from app.features.trading.models import Order, OrderStatus, Position
from app.features.trading.ports import OrderRepository, PositionRepository


class InMemoryOrderRepository(OrderRepository):
    def __init__(self) -> None:
        self._orders_by_client_id: dict[str, Order] = {}
        self._next_id = 1

    async def list_recent(self, limit: int = 50) -> list[Order]:
        return list(self._orders_by_client_id.values())[:limit]

    async def get_by_client_order_id(self, client_order_id: str) -> Order | None:
        return self._orders_by_client_id.get(client_order_id)

    async def add(self, order: Order) -> Order:
        order.id = self._next_id
        self._next_id += 1
        self._orders_by_client_id[order.client_order_id] = order
        return order

    async def update(self, order: Order) -> Order:
        self._orders_by_client_id[order.client_order_id] = order
        return order


class InMemoryPositionRepository(PositionRepository):
    def __init__(self) -> None:
        self._positions_by_symbol: dict[str, Position] = {}

    async def get_by_symbol(self, symbol: str) -> Position | None:
        return self._positions_by_symbol.get(symbol)

    async def upsert(self, position: Position) -> Position:
        self._positions_by_symbol[position.symbol] = position
        return position


class FakeBroker(BrokerAdapter):
    asset_class = AssetClass.KR_STOCK

    def __init__(self, result: OrderResult) -> None:
        self._result = result
        self.calls: list[OrderRequest] = []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self.calls.append(order)
        return self._result

    async def cancel_order(self, broker_order_id: str) -> OrderResult:
        raise NotImplementedError

    async def get_balance(self) -> Balance:
        raise NotImplementedError


@pytest.fixture
def orders() -> InMemoryOrderRepository:
    return InMemoryOrderRepository()


@pytest.fixture
def positions() -> InMemoryPositionRepository:
    return InMemoryPositionRepository()


async def test_submit_order_blocked_by_kill_switch_before_reaching_broker(orders, positions, kill_switch):
    await kill_switch.engage()
    guard = RiskGuard(kill_switch=kill_switch)
    broker = FakeBroker(OrderResult(broker_order_id="x", status="filled", filled_quantity=1, avg_fill_price=100))
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=broker)

    with pytest.raises(KillSwitchEngagedError):
        await facade.submit_order(symbol="005930", side="buy", asset_class="kr_stock", quantity=1)

    assert broker.calls == []  # 킬스위치에 걸리면 브로커까지 절대 도달하면 안 된다


async def test_submit_order_places_order_and_creates_position_on_buy_fill(orders, positions, kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)
    broker = FakeBroker(
        OrderResult(broker_order_id="broker-1", status="filled", filled_quantity=10, avg_fill_price=70_000)
    )
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=broker)

    order = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-1"
    )

    assert order.status == OrderStatus.FILLED
    assert len(broker.calls) == 1

    position = await positions.get_by_symbol("005930")
    assert position is not None
    assert position.quantity == 10
    assert position.avg_entry_price == 70_000


async def test_submit_order_is_idempotent_for_already_completed_orders(orders, positions, kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)
    broker = FakeBroker(
        OrderResult(broker_order_id="broker-1", status="filled", filled_quantity=10, avg_fill_price=70_000)
    )
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=broker)

    first = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-dup"
    )
    second = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-dup"
    )

    assert first.id == second.id
    assert len(broker.calls) == 1  # Celery 재시도를 흉내낸 두 번째 호출은 브로커까지 가면 안 된다 (멱등성)


async def test_submit_order_averages_entry_price_across_multiple_buys(orders, positions, kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)

    broker1 = FakeBroker(OrderResult(broker_order_id="b1", status="filled", filled_quantity=10, avg_fill_price=70_000))
    facade1 = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=broker1)
    await facade1.submit_order(symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-buy-1")

    broker2 = FakeBroker(OrderResult(broker_order_id="b2", status="filled", filled_quantity=10, avg_fill_price=90_000))
    facade2 = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=broker2)
    await facade2.submit_order(symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-buy-2")

    position = await positions.get_by_symbol("005930")
    assert position.quantity == 20
    assert position.avg_entry_price == 80_000  # (70,000*10 + 90,000*10) / 20


async def test_submit_order_records_realized_pnl_on_sell_fill(orders, positions, kill_switch, daily_pnl):
    guard = RiskGuard(kill_switch=kill_switch, daily_pnl=daily_pnl, daily_loss_limit_krw=None)

    buy_broker = FakeBroker(OrderResult(broker_order_id="b1", status="filled", filled_quantity=10, avg_fill_price=70_000))
    buy_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=buy_broker)
    await buy_facade.submit_order(symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-buy")

    sell_broker = FakeBroker(OrderResult(broker_order_id="b2", status="filled", filled_quantity=10, avg_fill_price=75_000))
    sell_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=sell_broker)
    await sell_facade.submit_order(symbol="005930", side="sell", asset_class="kr_stock", quantity=10, client_order_id="cid-sell")

    assert await daily_pnl.get_today_realized_pnl() == 50_000  # (75,000 - 70,000) * 10
    position = await positions.get_by_symbol("005930")
    assert position.quantity == 0
    assert position.avg_entry_price == 70_000  # 매도는 남은 수량 기준 평단가를 바꾸지 않는다


async def test_submit_order_engages_kill_switch_when_sell_fill_breaches_daily_loss_limit(
    orders, positions, kill_switch, daily_pnl
):
    guard = RiskGuard(kill_switch=kill_switch, daily_pnl=daily_pnl, daily_loss_limit_krw=100_000)

    buy_broker = FakeBroker(OrderResult(broker_order_id="b1", status="filled", filled_quantity=10, avg_fill_price=70_000))
    buy_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=buy_broker)
    await buy_facade.submit_order(symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-buy")

    # 200,000원 손실로 매도 체결 -> 일일 한도(100,000원) 초과 -> kill switch 자동 발동
    sell_broker = FakeBroker(OrderResult(broker_order_id="b2", status="filled", filled_quantity=10, avg_fill_price=50_000))
    sell_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=sell_broker)
    await sell_facade.submit_order(symbol="005930", side="sell", asset_class="kr_stock", quantity=10, client_order_id="cid-sell")

    assert await kill_switch.is_engaged() is True

    # 다음 주문부터는 즉시 차단되어야 한다
    with pytest.raises(KillSwitchEngagedError):
        await sell_facade.submit_order(symbol="005930", side="buy", asset_class="kr_stock", quantity=1, client_order_id="cid-next")
