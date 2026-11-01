"""Upbit REST 주문/계좌 어댑터.

Upbit은 KIS와 달리 OAuth 토큰 발급 절차가 없고, 매 요청마다 API Key/Secret으로
JWT를 서명해 Authorization 헤더에 싣는다. 모의투자 서버가 없으므로 TRADING_MODE=paper일
때는 이 어댑터를 아예 호출하지 않고 상위 레이어(risk.guard)에서 시뮬레이션 체결로
대체하는 것을 권장 — __init__에서 live=False면 명시적으로 막아 실수 주문을 방지한다.

심볼은 Upbit 마켓 코드 그대로 쓴다 (예: "KRW-BTC"). 원화 마켓만 지원한다 — 일일 손실
한도가 원화 기준이라 BTC/USDT 마켓 손익은 그대로 합산할 수 없기 때문이다.

Upbit 주문 유형과 우리 OrderRequest의 대응:
- 지정가 매수/매도: ord_type=limit, volume=수량, price=가격
- 시장가 매도: ord_type=market, volume=수량
- 시장가 매수: Upbit은 "수량"이 아니라 "총액(원)"으로만 시장가 매수를 받는다(ord_type=price).
  그래서 현재가(공개 ticker)로 수량 × 현재가를 계산해 총액으로 주문한다. 실제 체결 수량은
  가격 변동만큼 요청 수량과 조금 다를 수 있다.

체결 단가는 수수료를 반영한 실효 단가로 돌려준다 (매수: (체결금액+수수료)/수량,
매도: (체결금액-수수료)/수량). 그래야 포지션 평단과 실현손익, 그리고 일일 손실 한도가
수수료까지 포함한 실제 손익 기준으로 계산된다.
"""

import hashlib
import math
import uuid
from decimal import Decimal
from urllib.parse import unquote, urlencode

import httpx
import jwt

from app.core.config import get_settings
from app.core.exceptions import BrokerAPIError, RiskLimitExceededError, SymbolNotFoundError
from app.core.logging import get_logger
from app.features.broker.base import (
    AssetClass,
    Balance,
    BrokerAdapter,
    OrderRequest,
    OrderResult,
    Quote,
)

logger = get_logger(__name__)

UPBIT_BASE_URL = "https://api.upbit.com"
MIN_ORDER_KRW = 5000  # Upbit 원화 마켓 최소 주문 금액


def _fmt_number(value: float) -> str:
    """Upbit은 지수 표기(1e-05 등)를 거부하므로 고정소수점 문자열로 보낸다."""
    text = format(Decimal(str(value)).quantize(Decimal("0.00000001")).normalize(), "f")
    return text


class UpbitBrokerAdapter(BrokerAdapter):
    asset_class = AssetClass.CRYPTO

    def __init__(self, live: bool, http: httpx.AsyncClient | None = None) -> None:
        settings = get_settings()
        self._live = live
        self._access_key = settings.upbit_access_key
        self._secret_key = settings.upbit_secret_key
        self._http = http or httpx.AsyncClient(base_url=UPBIT_BASE_URL, timeout=5.0)

    def _require_live(self) -> None:
        if not self._live:
            raise NotImplementedError(
                "Upbit은 모의투자 서버가 없습니다. paper 모드에서는 risk.guard의 "
                "시뮬레이션 체결 경로를 사용하세요."
            )
        if not self._access_key or not self._secret_key:
            raise BrokerAPIError("UPBIT_ACCESS_KEY / UPBIT_SECRET_KEY가 비어 있습니다.")

    def _auth_headers(self, params: dict | None = None) -> dict:
        payload: dict = {"access_key": self._access_key, "nonce": str(uuid.uuid4())}
        if params:
            query_string = unquote(urlencode(params, doseq=True)).encode("utf-8")
            payload["query_hash"] = hashlib.sha512(query_string).hexdigest()
            payload["query_hash_alg"] = "SHA512"
        token = jwt.encode(payload, self._secret_key, algorithm="HS256")
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _raise_for_error(response: httpx.Response, action: str) -> dict | list:
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.status_code >= 400:
            error = data.get("error", {}) if isinstance(data, dict) else {}
            raise BrokerAPIError(
                f"Upbit {action} failed ({response.status_code}): "
                f"{error.get('name', '')} {error.get('message', response.text[:200])}"
            )
        return data

    async def _get_current_price(self, market: str) -> float:
        response = await self._http.get("/v1/ticker", params={"markets": market})
        data = self._raise_for_error(response, "ticker")
        if not data:
            raise BrokerAPIError(f"Upbit ticker returned no data for {market}")
        return float(data[0]["trade_price"])

    async def get_quote(self, symbol: str) -> Quote:
        """공개 ticker + 마켓 목록(한글 이름). 인증이 필요 없어 paper 모드에서도 쓸 수 있다."""
        response = await self._http.get("/v1/ticker", params={"markets": symbol})
        if response.status_code == 404:
            raise SymbolNotFoundError(f"업비트에 없는 마켓이에요: {symbol}")
        data = self._raise_for_error(response, "ticker")
        if not data:
            raise SymbolNotFoundError(f"업비트에 없는 마켓이에요: {symbol}")
        ticker = data[0]
        rate = ticker.get("signed_change_rate")
        return Quote(
            symbol=symbol,
            price=float(ticker["trade_price"]),
            name=await self._market_name(symbol),
            change_rate=round(float(rate) * 100, 2) if rate is not None else None,
        )

    async def _market_name(self, symbol: str) -> str | None:
        try:
            response = await self._http.get("/v1/market/all", params={"isDetails": "false"})
            markets = response.json() if response.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            return None
        return next((m.get("korean_name") for m in markets if m.get("market") == symbol), None)

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self._require_live()
        if not order.symbol.startswith("KRW-"):
            raise RiskLimitExceededError(f"원화 마켓(KRW-*)만 지원합니다: {order.symbol}")

        params: dict = {"market": order.symbol, "side": "bid" if order.side == "buy" else "ask"}
        if order.order_type == "limit":
            if order.price is None:
                raise RiskLimitExceededError("지정가 주문에는 price가 필요합니다.")
            params.update(ord_type="limit", volume=_fmt_number(order.quantity), price=_fmt_number(order.price))
            notional = order.quantity * order.price
        elif order.side == "buy":
            current = await self._get_current_price(order.symbol)
            notional = math.ceil(order.quantity * current)
            params.update(ord_type="price", price=str(notional))
        else:
            current = await self._get_current_price(order.symbol)
            notional = order.quantity * current
            params.update(ord_type="market", volume=_fmt_number(order.quantity))

        if notional < MIN_ORDER_KRW:
            # 재시도해도 해결되지 않는 문제라 BrokerAPIError(재시도 대상)가 아닌 리스크 오류로 올린다.
            raise RiskLimitExceededError(
                f"Upbit 최소 주문 금액({MIN_ORDER_KRW:,}원) 미만: 약 {notional:,.0f}원"
            )

        if order.client_order_id:
            params["identifier"] = order.client_order_id

        response = await self._http.post("/v1/orders", json=params, headers=self._auth_headers(params))
        if response.status_code >= 400 and order.client_order_id:
            # Celery 재시도로 같은 identifier가 다시 들어온 경우: 이전 시도가 실제로는
            # 접수됐을 수 있으니, 새로 주문하지 말고 기존 주문 상태를 그대로 돌려준다.
            existing = await self._find_by_identifier(order.client_order_id)
            if existing is not None:
                logger.info("Upbit order already exists for identifier %s", order.client_order_id)
                return existing
        data = self._raise_for_error(response, "place order")
        return self._to_result(data)

    async def _find_by_identifier(self, identifier: str) -> OrderResult | None:
        params = {"identifier": identifier}
        response = await self._http.get("/v1/order", params=params, headers=self._auth_headers(params))
        if response.status_code >= 400:
            return None
        return self._to_result(response.json())

    async def cancel_order(self, broker_order_id: str) -> OrderResult:
        self._require_live()
        params = {"uuid": broker_order_id}
        response = await self._http.delete("/v1/order", params=params, headers=self._auth_headers(params))
        self._raise_for_error(response, "cancel order")
        # 취소 응답은 취소 "요청" 시점 상태라, 최종 체결 수량은 다시 조회해서 돌려준다.
        result = await self.get_order_fill_status(broker_order_id)
        if result.status in ("accepted", "partially_filled"):
            return OrderResult(
                broker_order_id=broker_order_id,
                status="cancelled",
                filled_quantity=result.filled_quantity,
                avg_fill_price=result.avg_fill_price,
                raw=result.raw,
            )
        return result

    async def get_balance(self) -> Balance:
        self._require_live()
        response = await self._http.get("/v1/accounts", headers=self._auth_headers())
        data = self._raise_for_error(response, "accounts")
        cash = 0.0
        positions: dict[str, float] = {}
        for account in data:
            currency = account["currency"]
            balance = float(account["balance"])
            if currency == "KRW":
                cash = balance
            elif balance > 0 and account.get("unit_currency", "KRW") == "KRW":
                positions[f"KRW-{currency}"] = balance
        return Balance(cash=cash, positions=positions)

    async def get_order_fill_status(self, broker_order_id: str) -> OrderResult:
        self._require_live()
        params = {"uuid": broker_order_id}
        response = await self._http.get("/v1/order", params=params, headers=self._auth_headers(params))
        data = self._raise_for_error(response, "get order")
        return self._to_result(data)

    @staticmethod
    def _to_result(data: dict) -> OrderResult:
        """Upbit 주문 응답(state: wait/watch/done/cancel)을 공용 OrderResult로 변환한다."""
        state = data.get("state")
        ord_type = data.get("ord_type")
        executed = float(data.get("executed_volume") or 0)

        if state == "done":
            status = "filled"
        elif state == "cancel":
            # 시장가 매수(ord_type=price)는 총액을 다 쓰고 남은 끝전 때문에 체결 완료여도
            # state=cancel로 끝나는 경우가 흔하다 — 체결분이 있으면 체결 완료로 본다.
            if executed > 0 and ord_type in ("price", "market"):
                status = "filled"
            else:
                status = "cancelled"
        elif executed > 0:
            status = "partially_filled"
        else:
            status = "accepted"

        avg_price = None
        trades = data.get("trades") or []
        if executed > 0 and trades:
            volume = sum(float(t["volume"]) for t in trades)
            funds = sum(float(t["funds"]) for t in trades)
            fee = float(data.get("paid_fee") or 0)
            if volume > 0:
                net = funds + fee if data.get("side") == "bid" else funds - fee
                avg_price = net / volume

        if executed > 0 and avg_price is None:
            # 주문 생성 응답처럼 trades가 빠진 응답은 체결 단가를 알 수 없다. 여기서 최종
            # 상태(filled)로 기록해 버리면 체결 확인 폴링 대상에서 빠져 포지션/손익이 영영
            # 반영되지 않으므로, 접수 상태로 두고 다음 폴링에서 trades가 포함된 응답으로 확정한다.
            status = "accepted"

        return OrderResult(
            broker_order_id=data["uuid"],
            status=status,
            filled_quantity=executed if avg_price is not None else 0.0,
            avg_fill_price=avg_price,
            raw=data,
        )
