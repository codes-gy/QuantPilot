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

    async def list_pending(self) -> list[Order]:
        non_final = {OrderStatus.PENDING, OrderStatus.ACCEPTED, OrderStatus.PARTIALLY_FILLED}
        return [
            order
            for order in self._orders_by_client_id.values()
            if OrderStatus(order.status) in non_final and order.broker_order_id is not None
        ]

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

    def __init__(self, result: OrderResult, fill_status_results: list[OrderResult] | None = None) -> None:
        self._result = result
        # poll_and_apply_fill이 호출될 때마다 순서대로 하나씩 반환한다 (여러 폴링 사이클 시뮬레이션용).
        self._fill_status_results = list(fill_status_results or [])
        self.calls: list[OrderRequest] = []
        self.fill_status_calls: list[str] = []

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self.calls.append(order)
        return self._result

    async def cancel_order(self, broker_order_id: str) -> OrderResult:
        raise NotImplementedError

    async def get_balance(self) -> Balance:
        raise NotImplementedError

    async def get_order_fill_status(self, broker_order_id: str) -> OrderResult:
        self.fill_status_calls.append(broker_order_id)
        if not self._fill_status_results:
            raise AssertionError("get_order_fill_status called more times than fill_status_results provided")
        return self._fill_status_results.pop(0)


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


# --- 체결 확인 폴링 (KIS처럼 place_order 응답이 접수 확인뿐인 브로커용) ---


async def test_submit_order_with_accepted_only_response_does_not_update_position_yet(orders, positions, kill_switch):
    """KIS order-cash처럼 접수만 확인해주는 브로커는, submit_order() 시점에는 포지션을
    갱신하면 안 된다 (아직 체결 여부를 모르기 때문) — 이후 폴링이 담당해야 한다.
    """
    guard = RiskGuard(kill_switch=kill_switch)
    broker = FakeBroker(OrderResult(broker_order_id="b1", status="accepted"))
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=broker)

    order = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-accept"
    )

    assert order.status == OrderStatus.ACCEPTED
    assert await positions.get_by_symbol("005930") is None  # 아직 체결 확인 전이라 포지션 없음


async def test_pending_order_appears_in_list_pending_until_filled(orders, positions, kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)
    broker = FakeBroker(OrderResult(broker_order_id="b1", status="accepted"))
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=broker)

    order = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-pending"
    )

    pending = await orders.list_pending()
    assert [o.client_order_id for o in pending] == [order.client_order_id]


async def test_poll_and_apply_fill_updates_position_when_broker_reports_full_fill(orders, positions, kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)
    submit_broker = FakeBroker(OrderResult(broker_order_id="b1", status="accepted"))
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=submit_broker)
    order = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-poll"
    )
    assert await positions.get_by_symbol("005930") is None

    # 다음 폴링 사이클: 이번엔 전량 체결로 확인됨
    poll_broker = FakeBroker(
        OrderResult(broker_order_id="b1", status="accepted"),  # 사용 안 함
        fill_status_results=[
            OrderResult(broker_order_id="b1", status="filled", filled_quantity=10, avg_fill_price=70_000)
        ],
    )
    poll_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=poll_broker)
    updated = await poll_facade.poll_and_apply_fill(order)

    assert updated.status == OrderStatus.FILLED
    assert updated.filled_quantity == 10
    position = await positions.get_by_symbol("005930")
    assert position is not None
    assert position.quantity == 10
    assert position.avg_entry_price == 70_000

    # 체결이 끝났으니 더 이상 폴링 대상이 아니어야 한다
    assert await orders.list_pending() == []


async def test_poll_and_apply_fill_does_not_double_count_across_multiple_partial_fills(orders, positions, kill_switch):
    """같은 주문을 두 번의 폴링 사이클에 걸쳐 확인할 때(부분체결 -> 완전체결), 포지션에
    각 사이클의 '신규 체결분'만 반영되어야 한다 (누적치를 두 번 더하면 안 된다).
    """
    guard = RiskGuard(kill_switch=kill_switch)
    submit_broker = FakeBroker(OrderResult(broker_order_id="b1", status="accepted"))
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=submit_broker)
    order = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-partial"
    )

    # 1차 폴링: 10주 중 4주만 부분체결
    poll_broker = FakeBroker(
        OrderResult(broker_order_id="b1", status="accepted"),
        fill_status_results=[
            OrderResult(broker_order_id="b1", status="partially_filled", filled_quantity=4, avg_fill_price=70_000),
        ],
    )
    poll_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=poll_broker)
    order = await poll_facade.poll_and_apply_fill(order)

    assert order.status == OrderStatus.PARTIALLY_FILLED
    assert (await positions.get_by_symbol("005930")).quantity == 4

    # 2차 폴링: 누적 10주 전량 체결 (신규 체결분은 6주)
    poll_broker_2 = FakeBroker(
        OrderResult(broker_order_id="b1", status="accepted"),
        fill_status_results=[
            OrderResult(broker_order_id="b1", status="filled", filled_quantity=10, avg_fill_price=70_000),
        ],
    )
    poll_facade_2 = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=poll_broker_2)
    order = await poll_facade_2.poll_and_apply_fill(order)

    assert order.status == OrderStatus.FILLED
    position = await positions.get_by_symbol("005930")
    assert position.quantity == 10  # 4 + 6, 4 + 10이 아님 (중복 반영 안 됨)


async def test_poll_and_apply_fill_is_noop_when_broker_reports_no_change(orders, positions, kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)
    submit_broker = FakeBroker(OrderResult(broker_order_id="b1", status="accepted"))
    facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=submit_broker)
    order = await facade.submit_order(
        symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-nochange"
    )

    poll_broker = FakeBroker(
        OrderResult(broker_order_id="b1", status="accepted"),
        fill_status_results=[OrderResult(broker_order_id="b1", status="accepted")],  # 아직 그대로 미체결
    )
    poll_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=poll_broker)
    updated = await poll_facade.poll_and_apply_fill(order)

    assert updated.status == OrderStatus.ACCEPTED
    assert await positions.get_by_symbol("005930") is None


async def test_poll_and_apply_fill_engages_kill_switch_when_late_confirmed_sell_breaches_daily_limit(
    orders, positions, kill_switch, daily_pnl
):
    """매도 주문이 즉시 체결 응답 없이 접수만 됐다가, 나중에 폴링으로 체결이 확인되는
    경우에도 일일 손실 한도 서킷브레이커가 정상적으로 발동해야 한다.
    """
    guard = RiskGuard(kill_switch=kill_switch, daily_pnl=daily_pnl, daily_loss_limit_krw=100_000)

    # 매수로 포지션을 미리 만들어둔다 (즉시 체결)
    buy_broker = FakeBroker(OrderResult(broker_order_id="b1", status="filled", filled_quantity=10, avg_fill_price=70_000))
    buy_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=buy_broker)
    await buy_facade.submit_order(symbol="005930", side="buy", asset_class="kr_stock", quantity=10, client_order_id="cid-buy")

    # 매도 주문은 접수만 확인됨
    sell_submit_broker = FakeBroker(OrderResult(broker_order_id="b2", status="accepted"))
    sell_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=sell_submit_broker)
    sell_order = await sell_facade.submit_order(
        symbol="005930", side="sell", asset_class="kr_stock", quantity=10, client_order_id="cid-sell"
    )
    assert await kill_switch.is_engaged() is False  # 아직 체결 확인 전

    # 폴링으로 200,000원 손실 체결이 뒤늦게 확인됨 -> 한도 초과 -> kill switch 발동
    poll_broker = FakeBroker(
        OrderResult(broker_order_id="b2", status="accepted"),
        fill_status_results=[
            OrderResult(broker_order_id="b2", status="filled", filled_quantity=10, avg_fill_price=50_000)
        ],
    )
    poll_facade = OrderExecutionFacade(orders=orders, positions=positions, risk_guard=guard, broker=poll_broker)
    await poll_facade.poll_and_apply_fill(sell_order)

    assert await kill_switch.is_engaged() is True
