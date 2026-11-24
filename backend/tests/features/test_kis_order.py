"""KISBrokerAdapter 주문 제출 실패 분류와 미확정 주문 대사(find_order) 테스트.

httpx.MockTransport로 KIS 응답(과 네트워크 오류)을 흉내 낸다. 핵심은 "요청이 나간 뒤
응답을 못 받은 경우"를 재시도 가능한 BrokerAPIError가 아니라 OrderOutcomeUnknownError로
구분하는 것이다 — 그래야 Celery autoretry가 같은 주문을 다시 보내지 않는다.
"""

from datetime import UTC, datetime

import httpx
import pytest

from app.core.exceptions import BrokerAPIError, OrderOutcomeUnknownError
from app.features.broker.base import OrderRequest
from app.features.broker.kis.client import KISBrokerAdapter

ORDER = OrderRequest(symbol="005930", side="buy", order_type="market", quantity=10, client_order_id="cid-1")


def _adapter(handler) -> KISBrokerAdapter:
    http = httpx.AsyncClient(base_url="https://kis.test", transport=httpx.MockTransport(handler))
    adapter = KISBrokerAdapter(live=False, http=http)
    adapter._creds.account_no = "12345678-01"

    async def fake_headers(tr_id: str) -> dict:
        return {"tr_id": tr_id}  # 토큰 발급(네트워크) 없이 TR ID만 실어 보낸다

    adapter._headers = fake_headers
    return adapter


def _raising(exc_type):
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc_type("boom", request=request)

    return handler


# --- place_order 실패 분류 ---


@pytest.mark.parametrize(
    "exc_type", [httpx.ReadTimeout, httpx.WriteTimeout, httpx.ReadError, httpx.RemoteProtocolError]
)
async def test_response_lost_after_send_is_unknown(exc_type):
    with pytest.raises(OrderOutcomeUnknownError):
        await _adapter(_raising(exc_type)).place_order(ORDER)


@pytest.mark.parametrize("exc_type", [httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout])
async def test_failure_before_send_is_retryable_broker_error(exc_type):
    with pytest.raises(BrokerAPIError):
        await _adapter(_raising(exc_type)).place_order(ORDER)


async def test_unparseable_success_response_is_unknown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>gateway</html>")

    with pytest.raises(OrderOutcomeUnknownError):
        await _adapter(handler).place_order(ORDER)


async def test_gateway_5xx_without_json_is_unknown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    with pytest.raises(OrderOutcomeUnknownError):
        await _adapter(handler).place_order(ORDER)


async def test_success_without_order_number_is_unknown():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"rt_cd": "0", "output": {}})

    with pytest.raises(OrderOutcomeUnknownError):
        await _adapter(handler).place_order(ORDER)


async def test_explicit_rejection_is_broker_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"rt_cd": "1", "msg1": "초당 거래건수를 초과하였습니다."})

    with pytest.raises(BrokerAPIError, match="초당"):
        await _adapter(handler).place_order(ORDER)


async def test_accepted_order_returns_combined_broker_order_id():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["tr_id"] == "VTTC0802U"
        return httpx.Response(
            200, json={"rt_cd": "0", "output": {"KRX_FWDG_ORD_ORGNO": "91252", "ODNO": "0000117057"}}
        )

    result = await _adapter(handler).place_order(ORDER)

    assert (result.broker_order_id, result.status) == ("91252:0000117057", "accepted")


# --- find_order (당일 주문체결조회 대사) ---

PLACED_AFTER = datetime(2026, 11, 25, 0, 59, 30, tzinfo=UTC)  # KST 09:59:30


def _row(**overrides) -> dict:
    row = {
        "ord_dt": "20261125",
        "ord_tmd": "100000",  # KST 10:00:00
        "odno": "0000117057",
        "ord_gno_brno": "91252",
        "orgn_odno": "",
        "sll_buy_dvsn_cd": "02",
        "pdno": "005930",
        "ord_qty": "10",
        "tot_ccld_qty": "0",
        "avg_prvs": "0",
    }
    row.update(overrides)
    return row


def _ccld(rows: list[dict], tr_cont: str = "D"):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["params"] = dict(request.url.params)
        return httpx.Response(200, json={"rt_cd": "0", "output1": rows}, headers={"tr_cont": tr_cont})

    return handler, seen


async def test_find_order_returns_single_match():
    handler, seen = _ccld([_row(tot_ccld_qty="10", avg_prvs="70000")])

    result = await _adapter(handler).find_order(ORDER, placed_after=PLACED_AFTER)

    assert result.broker_order_id == "91252:0000117057"
    assert (result.status, result.filled_quantity, result.avg_fill_price) == ("filled", 10, 70_000)
    assert seen["params"]["PDNO"] == "005930"
    assert seen["params"]["SLL_BUY_DVSN_CD"] == "02"
    assert seen["params"]["INQR_STRT_DT"] == "20261125"


async def test_find_order_ignores_non_matching_rows():
    handler, _ = _ccld(
        [
            _row(ord_tmd="095900", odno="1"),  # 주문 시각 이전
            _row(ord_qty="5", odno="2"),  # 수량 다름
            _row(sll_buy_dvsn_cd="01", odno="3"),  # 매도
            _row(orgn_odno="0000000001", odno="4"),  # 취소/정정 주문 행
        ]
    )

    assert await _adapter(handler).find_order(ORDER, placed_after=PLACED_AFTER) is None


async def test_find_order_excludes_orders_already_linked_to_other_records():
    handler, _ = _ccld([_row(odno="0000117057"), _row(odno="0000117060", ord_tmd="100005")])

    result = await _adapter(handler).find_order(
        ORDER, placed_after=PLACED_AFTER, exclude_broker_order_ids=frozenset({"91252:117057"})
    )

    assert result.broker_order_id == "91252:0000117060"


async def test_find_order_with_multiple_candidates_is_inconclusive():
    handler, _ = _ccld([_row(odno="1"), _row(odno="2")])

    with pytest.raises(OrderOutcomeUnknownError):
        await _adapter(handler).find_order(ORDER, placed_after=PLACED_AFTER)


async def test_find_order_not_found_but_more_pages_is_inconclusive():
    handler, _ = _ccld([], tr_cont="M")

    with pytest.raises(OrderOutcomeUnknownError):
        await _adapter(handler).find_order(ORDER, placed_after=PLACED_AFTER)


async def test_find_order_network_error_is_broker_error():
    with pytest.raises(BrokerAPIError):
        await _adapter(_raising(httpx.ReadTimeout)).find_order(ORDER, placed_after=PLACED_AFTER)
