"""주문 응답 유실(UNKNOWN) -> 재전송 금지 -> 브로커 조회로 대사하는 흐름 테스트.

핵심 시나리오: 브로커는 주문을 받았는데 응답이 유실됐다(타임아웃). 예전에는 주문이
PENDING으로 남아 Celery 재시도나 전략 러너의 새 주문으로 같은 주문이 한 번 더 나갈 수 있었다.
이제는 UNKNOWN으로 남고, 브로커 주문 조회로 확정되기 전까지 다시 보내지 않아야 한다.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import BrokerAPIError, OrderOutcomeUnknownError, RiskLimitExceededError
from app.features.broker.base import AssetClass, Balance, BrokerAdapter, OrderRequest, OrderResult
from app.features.risk.guard import RiskGuard
from app.features.trading.facade import OrderExecutionFacade
from app.features.trading.models import OrderStatus
from tests.features.conftest import RecordingNotifier
from tests.features.test_order_execution_facade import (
    InMemoryOrderRepository,
    InMemoryPositionRepository,
)


class ScriptedBroker(BrokerAdapter):
    """place_order/find_order/cancel_order 결과를 순서대로 돌려주는 가짜 브로커.
    결과 자리에 예외 인스턴스를 넣으면 그 예외를 던진다.
    """

    asset_class = AssetClass.KR_STOCK

    def __init__(self, *, place=(), find=(), fill_status=(), cancel=()) -> None:
        self._place = list(place)
        self._find = list(find)
        self._fill_status = list(fill_status)
        self._cancel = list(cancel)
        self.place_calls: list[OrderRequest] = []
        self.find_calls: list[dict] = []
        self.cancel_calls: list[str] = []

    @staticmethod
    def _next(queue: list, name: str):
        if not queue:
            raise AssertionError(f"{name} called more times than scripted")
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self.place_calls.append(order)
        return self._next(self._place, "place_order")

    async def find_order(self, order, *, placed_after, exclude_broker_order_ids=frozenset()):
        self.find_calls.append(
            {"order": order, "placed_after": placed_after, "exclude": exclude_broker_order_ids}
        )
        return self._next(self._find, "find_order")

    async def cancel_order(self, broker_order_id: str) -> OrderResult:
        self.cancel_calls.append(broker_order_id)
        return self._next(self._cancel, "cancel_order")

    async def get_order_fill_status(self, broker_order_id: str) -> OrderResult:
        return self._next(self._fill_status, "get_order_fill_status")

    async def get_balance(self) -> Balance:
        raise NotImplementedError


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 11, 25, 1, 0, 0)  # naive UTC (모델과 같은 형식)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> datetime:
        self.now += timedelta(**kwargs)
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def orders(clock) -> InMemoryOrderRepository:
    repo = InMemoryOrderRepository()
    repo.clock = clock
    return repo


@pytest.fixture
def positions() -> InMemoryPositionRepository:
    return InMemoryPositionRepository()


def _facade(orders, positions, kill_switch, broker, notifier=None) -> OrderExecutionFacade:
    return OrderExecutionFacade(
        orders=orders,
        positions=positions,
        risk_guard=RiskGuard(kill_switch=kill_switch),
        broker=broker,
        notifier=notifier,
    )


async def _submit(facade: OrderExecutionFacade, cid: str = "cid-1", **overrides):
    kwargs = {"symbol": "005930", "side": "buy", "asset_class": "kr_stock", "quantity": 10}
    kwargs.update(overrides)
    return await facade.submit_order(client_order_id=cid, **kwargs)


# --- 제출 단계 ---


async def test_lost_response_leaves_order_unknown_without_raising(orders, positions, kill_switch):
    notifier = RecordingNotifier()
    broker = ScriptedBroker(place=[OrderOutcomeUnknownError("read timeout")])
    facade = _facade(orders, positions, kill_switch, broker, notifier)

    order = await _submit(facade)

    assert order.status == OrderStatus.UNKNOWN
    assert order.broker_order_id is None
    assert [event for event, _ in notifier.events] == ["order_state_unknown"]


async def test_retry_after_lost_response_does_not_resend(orders, positions, kill_switch):
    """Celery 재시도나 중복 호출로 같은 client_order_id가 다시 와도 브로커에 다시 보내지 않는다."""
    broker = ScriptedBroker(place=[OrderOutcomeUnknownError("read timeout")])
    facade = _facade(orders, positions, kill_switch, broker)

    await _submit(facade)
    again = await _submit(facade)

    assert again.status == OrderStatus.UNKNOWN
    assert len(broker.place_calls) == 1


async def test_order_is_marked_unknown_before_broker_call(orders, positions, kill_switch):
    """전송 직전에 UNKNOWN으로 저장해야, 그 사이 워커가 죽어도 재전송 대상이 되지 않는다."""
    broker = ScriptedBroker(place=[OrderResult(broker_order_id="b1", status="accepted")])
    facade = _facade(orders, positions, kill_switch, broker)

    await _submit(facade)

    assert orders.status_history["cid-1"] == ["pending", "unknown", "accepted"]


async def test_crash_during_send_keeps_order_unknown(orders, positions, kill_switch):
    broker = ScriptedBroker(place=[RuntimeError("worker died mid-flight")])
    facade = _facade(orders, positions, kill_switch, broker)

    with pytest.raises(RuntimeError):
        await _submit(facade)

    order = await orders.get_by_client_order_id("cid-1")
    assert order.status == OrderStatus.UNKNOWN
    assert await orders.list_unknown() == [order]


async def test_definitive_failure_reverts_to_pending_and_retry_resends(orders, positions, kill_switch):
    """브로커가 명시적으로 거부했거나 전송 전에 실패한 경우에만 같은 주문을 다시 보낸다."""
    broker = ScriptedBroker(
        place=[BrokerAPIError("rate limited"), OrderResult(broker_order_id="b1", status="accepted")]
    )
    facade = _facade(orders, positions, kill_switch, broker)

    with pytest.raises(BrokerAPIError):
        await _submit(facade)
    assert (await orders.get_by_client_order_id("cid-1")).status == OrderStatus.PENDING

    retried = await _submit(facade)

    assert retried.status == OrderStatus.ACCEPTED
    assert len(broker.place_calls) == 2
    assert len(await orders.list_recent()) == 1  # 같은 주문 레코드를 재사용한다


async def test_adapter_side_risk_rejection_is_final(orders, positions, kill_switch):
    broker = ScriptedBroker(place=[RiskLimitExceededError("below minimum order")])
    facade = _facade(orders, positions, kill_switch, broker)

    with pytest.raises(RiskLimitExceededError):
        await _submit(facade)

    assert (await orders.get_by_client_order_id("cid-1")).status == OrderStatus.REJECTED


# --- 대사 단계 ---


async def _unknown_order(orders, positions, kill_switch):
    broker = ScriptedBroker(place=[OrderOutcomeUnknownError("read timeout")])
    return await _submit(_facade(orders, positions, kill_switch, broker))


async def test_reconcile_skips_orders_that_may_still_be_in_flight(orders, positions, kill_switch, clock):
    order = await _unknown_order(orders, positions, kill_switch)
    broker = ScriptedBroker()
    clock.advance(seconds=5)

    result = await _facade(orders, positions, kill_switch, broker).reconcile_unknown_order(order, now=clock())

    assert result.status == OrderStatus.UNKNOWN
    assert broker.find_calls == []


async def test_reconcile_adopts_order_found_at_broker(orders, positions, kill_switch, clock):
    """응답은 유실됐지만 브로커에는 접수돼 있던 경우: 새로 주문하지 않고 그 주문을 이어받는다."""
    order = await _unknown_order(orders, positions, kill_switch)
    broker = ScriptedBroker(find=[OrderResult(broker_order_id="ORG:0001", status="accepted")])
    clock.advance(minutes=1)

    result = await _facade(orders, positions, kill_switch, broker).reconcile_unknown_order(order, now=clock())

    assert result.status == OrderStatus.ACCEPTED
    assert result.broker_order_id == "ORG:0001"
    assert await orders.list_pending() == [result]  # 이제 일반 체결 폴링 대상
    assert await orders.list_unknown() == []
    assert broker.place_calls == []

    call = broker.find_calls[0]
    assert call["order"].client_order_id == "cid-1"
    assert call["placed_after"].tzinfo is not None
    assert call["placed_after"] <= order.created_at.replace(tzinfo=UTC)


async def test_reconcile_applies_fill_found_at_broker(orders, positions, kill_switch, clock):
    order = await _unknown_order(orders, positions, kill_switch)
    broker = ScriptedBroker(
        find=[OrderResult(broker_order_id="ORG:0001", status="filled", filled_quantity=10, avg_fill_price=70_000)]
    )
    clock.advance(minutes=1)

    result = await _facade(orders, positions, kill_switch, broker).reconcile_unknown_order(order, now=clock())

    assert result.status == OrderStatus.FILLED
    position = await positions.get_by_symbol("005930")
    assert (position.quantity, position.avg_entry_price) == (10, 70_000)


async def test_reconcile_excludes_broker_orders_owned_by_other_records(orders, positions, kill_switch, clock):
    other = ScriptedBroker(place=[OrderResult(broker_order_id="ORG:0009", status="accepted")])
    await _submit(_facade(orders, positions, kill_switch, other), cid="cid-other")
    order = await _unknown_order(orders, positions, kill_switch)
    broker = ScriptedBroker(find=[None])
    clock.advance(minutes=1)

    await _facade(orders, positions, kill_switch, broker).reconcile_unknown_order(order, now=clock())

    assert broker.find_calls[0]["exclude"] == frozenset({"ORG:0009"})


async def test_reconcile_not_found_waits_for_grace_period_then_rejects(orders, positions, kill_switch, clock):
    order = await _unknown_order(orders, positions, kill_switch)
    broker = ScriptedBroker(find=[None, None])
    facade = _facade(orders, positions, kill_switch, broker)

    clock.advance(minutes=1)
    assert (await facade.reconcile_unknown_order(order, now=clock())).status == OrderStatus.UNKNOWN

    clock.advance(minutes=2)
    result = await facade.reconcile_unknown_order(order, now=clock())

    assert result.status == OrderStatus.REJECTED  # 접수 기록 없음으로 확정 -> 이후 새 신호로만 재주문
    assert broker.place_calls == []


@pytest.mark.parametrize(
    "outcome",
    [
        OrderOutcomeUnknownError("2 candidates"),
        BrokerAPIError("inquiry failed"),
        NotImplementedError(),
    ],
)
async def test_reconcile_keeps_unknown_when_inconclusive(orders, positions, kill_switch, clock, outcome):
    order = await _unknown_order(orders, positions, kill_switch)
    broker = ScriptedBroker(find=[outcome])
    clock.advance(minutes=10)

    result = await _facade(orders, positions, kill_switch, broker).reconcile_unknown_order(order, now=clock())

    assert result.status == OrderStatus.UNKNOWN
    assert broker.place_calls == []


# --- kill switch 발동 시 미체결 주문 취소 ---


async def test_cancel_open_order_applies_fills_that_landed_before_cancel(orders, positions, kill_switch):
    submit = ScriptedBroker(place=[OrderResult(broker_order_id="b1", status="accepted")])
    order = await _submit(_facade(orders, positions, kill_switch, submit))
    broker = ScriptedBroker(
        cancel=[OrderResult(broker_order_id="b1", status="cancelled")],
        fill_status=[
            OrderResult(broker_order_id="b1", status="partially_filled", filled_quantity=4, avg_fill_price=70_000)
        ],
    )

    result = await _facade(orders, positions, kill_switch, broker).cancel_open_order(order)

    assert broker.cancel_calls == ["b1"]
    assert result.status == OrderStatus.CANCELLED
    assert result.filled_quantity == 4
    assert (await positions.get_by_symbol("005930")).quantity == 4
    assert await orders.list_pending() == []


async def test_cancel_open_order_marks_filled_if_fully_filled_first(orders, positions, kill_switch):
    submit = ScriptedBroker(place=[OrderResult(broker_order_id="b1", status="accepted")])
    order = await _submit(_facade(orders, positions, kill_switch, submit))
    broker = ScriptedBroker(
        cancel=[OrderResult(broker_order_id="b1", status="cancelled")],
        fill_status=[OrderResult(broker_order_id="b1", status="filled", filled_quantity=10, avg_fill_price=70_000)],
    )

    result = await _facade(orders, positions, kill_switch, broker).cancel_open_order(order)

    assert result.status == OrderStatus.FILLED
