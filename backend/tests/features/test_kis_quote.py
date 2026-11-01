"""KISBrokerAdapter.get_quote 단위 테스트 — httpx.MockTransport로 KIS 응답을 흉내 낸다."""

import httpx
import pytest

from app.core.exceptions import BrokerAPIError, SymbolNotFoundError
from app.features.broker.kis.client import KISBrokerAdapter


def _adapter(handler) -> KISBrokerAdapter:
    adapter = KISBrokerAdapter(live=True)
    adapter._http = httpx.AsyncClient(base_url="https://kis.test", transport=httpx.MockTransport(handler))

    async def fake_headers(tr_id: str) -> dict:
        return {"tr_id": tr_id}  # 토큰 발급(네트워크) 없이 TR ID만 실어 보낸다

    adapter._headers = fake_headers
    return adapter


def _price(prpr: str, rate: str = "-4.96") -> dict:
    return {"rt_cd": "0", "msg1": "정상처리 되었습니다.", "output": {"stck_prpr": prpr, "prdy_ctrt": rate}}


async def test_quote_with_name():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["tr_id"] == "FHKST01010100":
            assert request.url.params["FID_INPUT_ISCD"] == "005930"
            return httpx.Response(200, json=_price("220500"))
        assert request.headers["tr_id"] == "CTPF1002R"
        return httpx.Response(200, json={"rt_cd": "0", "output": {"prdt_abrv_name": "삼성전자"}})

    quote = await _adapter(handler).get_quote("005930")
    assert (quote.symbol, quote.price, quote.name, quote.change_rate) == ("005930", 220500.0, "삼성전자", -4.96)


async def test_unknown_symbol_is_detected_from_zero_price():
    # KIS는 없는 종목코드에도 rt_cd=0으로 응답하고 현재가만 0으로 준다 (실서버에서 확인)
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_price("0", ""))

    with pytest.raises(SymbolNotFoundError):
        await _adapter(handler).get_quote("999999")


async def test_name_lookup_failure_keeps_price():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers["tr_id"] == "FHKST01010100":
            return httpx.Response(200, json=_price("7120", "1.5"))
        return httpx.Response(200, json={"rt_cd": "1", "msg1": "조회 실패"})

    quote = await _adapter(handler).get_quote("000000")
    assert quote.price == 7120.0
    assert quote.name is None
    assert quote.change_rate == 1.5


async def test_api_error_raises_broker_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"rt_cd": "1", "msg1": "서버 오류"})

    with pytest.raises(BrokerAPIError):
        await _adapter(handler).get_quote("005930")
