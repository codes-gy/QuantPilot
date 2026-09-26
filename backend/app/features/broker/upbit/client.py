"""Upbit REST 주문/계좌 어댑터.

Upbit은 KIS와 달리 OAuth 토큰 발급 절차가 없고, 매 요청마다 API Key/Secret으로
JWT를 서명해 Authorization 헤더에 싣는다. 모의투자 서버가 없으므로 TRADING_MODE=paper일
때는 이 어댑터를 아예 호출하지 않고 상위 레이어(risk.guard)에서 시뮬레이션 체결로
대체하는 것을 권장 — __init__에서 live=False면 명시적으로 막아 실수 주문을 방지한다.
"""

import httpx

from app.core.config import get_settings
from app.features.broker.base import AssetClass, Balance, BrokerAdapter, OrderRequest, OrderResult

UPBIT_BASE_URL = "https://api.upbit.com"


class UpbitBrokerAdapter(BrokerAdapter):
    asset_class = AssetClass.CRYPTO

    def __init__(self, live: bool) -> None:
        settings = get_settings()
        self._live = live
        self._access_key = settings.upbit_access_key
        self._secret_key = settings.upbit_secret_key
        self._http = httpx.AsyncClient(base_url=UPBIT_BASE_URL, timeout=5.0)

    def _require_live(self) -> None:
        if not self._live:
            raise NotImplementedError(
                "Upbit은 모의투자 서버가 없습니다. paper 모드에서는 risk.guard의 "
                "시뮬레이션 체결 경로를 사용하세요."
            )

    async def place_order(self, order: OrderRequest) -> OrderResult:
        self._require_live()
        # TODO: POST /v1/orders (JWT: access_key, nonce, query_hash)
        raise NotImplementedError

    async def cancel_order(self, broker_order_id: str) -> OrderResult:
        self._require_live()
        # TODO: DELETE /v1/order
        raise NotImplementedError

    async def get_balance(self) -> Balance:
        self._require_live()
        # TODO: GET /v1/accounts
        raise NotImplementedError

    async def get_order_fill_status(self, broker_order_id: str) -> OrderResult:
        self._require_live()
        # TODO: GET /v1/order (Upbit은 주문 즉시 체결 응답을 포함하는 경우가 많아, KIS만큼
        # 폴링이 필수는 아닐 수 있다 — 실제 연동 시 place_order 응답부터 다시 확인할 것)
        raise NotImplementedError
