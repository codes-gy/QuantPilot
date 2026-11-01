"""UpbitBrokerAdapter / UpbitMarketDataAdapter 단위 테스트.

실제 Upbit 서버 대신 httpx.MockTransport로 응답을 흉내 낸다 — 네트워크 호출이나
실제 주문은 일어나지 않는다.
"""

import hashlib
import json
from urllib.parse import unquote, urlencode

import httpx
import jwt
import pytest

from app.core.exceptions import BrokerAPIError, RiskLimitExceededError
from app.features.broker.base import OrderRequest
from app.features.broker.upbit.client import UPBIT_BASE_URL, UpbitBrokerAdapter, _fmt_number
from app.features.broker.upbit.ws_client import UpbitMarketDataAdapter

ACCESS = "test-access-key"
SECRET = "test-secret-key"


def _adapter(handler, live: bool = True) -> UpbitBrokerAdapter:
    http = httpx.AsyncClient(base_url=UPBIT_BASE_URL, transport=httpx.MockTransport(handler))
    adapter = UpbitBrokerAdapter(live=live, http=http)
    adapter._access_key = ACCESS
    adapter._secret_key = SECRET
    return adapter


def _claims(request: httpx.Request) -> dict:
    token = request.headers["Authorization"].removeprefix("Bearer ")
    return jwt.decode(token, SECRET, algorithms=["HS256"])


def _order(**overrides) -> dict:
    base = {
        "uuid": "u-1",
        "side": "bid",
        "ord_type": "price",
        "state": "wait",
        "executed_volume": "0",
        "paid_fee": "0",
        "trades": [],
    }
    base.update(overrides)
    return base


async def test_market_buy_sends_krw_amount_with_signed_query_hash():
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/ticker":
            return httpx.Response(200, json=[{"market": "KRW-BTC", "trade_price": 100000}])
        sent["body"] = json.loads(request.content)
        sent["claims"] = _claims(request)
        return httpx.Response(201, json=_order())

    result = await _adapter(handler).place_order(
        OrderRequest(symbol="KRW-BTC", side="buy", order_type="market", quantity=0.1, client_order_id="cid-1")
    )

    body = sent["body"]
    assert body == {
        "market": "KRW-BTC",
        "side": "bid",
        "ord_type": "price",
        "price": "10000",
        "identifier": "cid-1",
    }
    expected_hash = hashlib.sha512(unquote(urlencode(body)).encode()).hexdigest()
    assert sent["claims"]["access_key"] == ACCESS
    assert sent["claims"]["query_hash"] == expected_hash
    assert result.status == "accepted"
    assert result.broker_order_id == "u-1"


async def test_market_sell_sends_volume():
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/ticker":
            return httpx.Response(200, json=[{"trade_price": 100000}])
        sent["body"] = json.loads(request.content)
        return httpx.Response(201, json=_order(side="ask", ord_type="market"))

    await _adapter(handler).place_order(
        OrderRequest(symbol="KRW-BTC", side="sell", order_type="market", quantity=0.06)
    )
    assert sent["body"]["ord_type"] == "market"
    assert sent["body"]["volume"] == "0.06"
    assert "price" not in sent["body"]


async def test_order_below_minimum_is_rejected_without_posting():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/ticker":
            return httpx.Response(200, json=[{"trade_price": 100000}])
        raise AssertionError("최소 금액 미만 주문은 전송되면 안 된다")

    with pytest.raises(RiskLimitExceededError):
        await _adapter(handler).place_order(
            OrderRequest(symbol="KRW-BTC", side="buy", order_type="market", quantity=0.01)
        )


async def test_non_krw_market_is_rejected():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("요청이 나가면 안 된다")

    with pytest.raises(RiskLimitExceededError):
        await _adapter(handler).place_order(
            OrderRequest(symbol="BTC-ETH", side="buy", order_type="limit", quantity=1, price=0.05)
        )


async def test_paper_mode_never_calls_upbit():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("paper 모드에서 Upbit 호출 금지")

    with pytest.raises(NotImplementedError):
        await _adapter(handler, live=False).place_order(
            OrderRequest(symbol="KRW-BTC", side="buy", order_type="market", quantity=1)
        )


async def test_retry_with_same_identifier_returns_existing_order():
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.url.path == "/v1/ticker":
            return httpx.Response(200, json=[{"trade_price": 100000}])
        if request.method == "POST":
            return httpx.Response(400, json={"error": {"name": "duplicate_identifier", "message": "dup"}})
        assert request.url.params["identifier"] == "cid-1"
        return httpx.Response(200, json=_order(uuid="u-existing"))

    result = await _adapter(handler).place_order(
        OrderRequest(symbol="KRW-BTC", side="buy", order_type="market", quantity=0.1, client_order_id="cid-1")
    )
    assert result.broker_order_id == "u-existing"
    assert calls.count("POST /v1/orders") == 1


async def test_api_error_raises_broker_error():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/ticker":
            return httpx.Response(200, json=[{"trade_price": 100000}])
        if request.method == "POST":
            return httpx.Response(400, json={"error": {"name": "insufficient_funds_bid", "message": "잔고 부족"}})
        return httpx.Response(404, json={"error": {"name": "order_not_found"}})

    with pytest.raises(BrokerAPIError, match="insufficient_funds_bid"):
        await _adapter(handler).place_order(
            OrderRequest(symbol="KRW-BTC", side="buy", order_type="market", quantity=0.1, client_order_id="c")
        )


def test_market_buy_ending_in_cancel_state_counts_as_filled_with_fee_in_price():
    result = UpbitBrokerAdapter._to_result(
        _order(
            state="cancel",
            executed_volume="0.1",
            paid_fee="5",
            trades=[{"volume": "0.1", "funds": "10000"}],
        )
    )
    assert result.status == "filled"
    assert result.filled_quantity == pytest.approx(0.1)
    assert result.avg_fill_price == pytest.approx(100050)  # (10000 + 5) / 0.1


def test_sell_fill_price_is_net_of_fee():
    result = UpbitBrokerAdapter._to_result(
        _order(
            side="ask",
            ord_type="market",
            state="done",
            executed_volume="0.1",
            paid_fee="5",
            trades=[{"volume": "0.1", "funds": "10000"}],
        )
    )
    assert result.avg_fill_price == pytest.approx(99950)  # (10000 - 5) / 0.1


def test_executed_without_trades_stays_accepted_for_polling():
    result = UpbitBrokerAdapter._to_result(_order(state="done", executed_volume="0.1", trades=[]))
    assert result.status == "accepted"
    assert result.filled_quantity == 0.0


def test_partially_filled_limit_order_cancelled():
    result = UpbitBrokerAdapter._to_result(
        _order(
            ord_type="limit",
            state="cancel",
            executed_volume="0.05",
            trades=[{"volume": "0.05", "funds": "5000"}],
        )
    )
    assert result.status == "cancelled"
    assert result.filled_quantity == pytest.approx(0.05)


async def test_balance_maps_krw_markets():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[
                {"currency": "KRW", "balance": "55.6", "unit_currency": "KRW"},
                {"currency": "BTC", "balance": "0.001", "unit_currency": "KRW"},
                {"currency": "ETH", "balance": "0", "unit_currency": "KRW"},
            ],
        )

    balance = await _adapter(handler).get_balance()
    assert balance.cash == pytest.approx(55.6)
    assert balance.positions == {"KRW-BTC": 0.001}


def test_fmt_number_never_uses_exponent():
    assert _fmt_number(0.00001) == "0.00001"
    assert _fmt_number(270.58301486) == "270.58301486"
    assert _fmt_number(10.0) == "10"


def test_ws_parses_binary_trade_frame():
    raw = json.dumps(
        {"type": "trade", "code": "KRW-BTC", "trade_price": 100000.0, "trade_volume": 0.5, "trade_timestamp": 1700000000000}
    ).encode()
    tick = UpbitMarketDataAdapter.parse_message(raw)
    assert tick is not None
    assert (tick.symbol, tick.price, tick.volume, tick.timestamp) == ("KRW-BTC", 100000.0, 0.5, 1700000000.0)


def test_ws_ignores_status_and_raises_on_error():
    assert UpbitMarketDataAdapter.parse_message(b'{"status":"UP"}') is None
    with pytest.raises(BrokerAPIError):
        UpbitMarketDataAdapter.parse_message(b'{"error":{"name":"INVALID_PARAM"}}')
