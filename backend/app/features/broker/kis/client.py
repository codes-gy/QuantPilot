"""한국투자증권 REST 주문/계좌 어댑터.

paper(모의투자)와 live(실전투자)는 base_url, app_key/secret, TR_ID 접두어가 전부 달라
동일 클래스를 credential 세트만 바꿔 재사용한다. live 여부는 반드시 factory.py를 통해서만
결정되며 이 클래스 스스로 TRADING_MODE를 읽지 않는다 (실수 방지).
"""

import httpx

from app.core.config import get_settings
from app.features.broker.base import AssetClass, Balance, BrokerAdapter, OrderRequest, OrderResult
from app.features.broker.kis.auth import KISAuth, KISCredentials


class KISBrokerAdapter(BrokerAdapter):
    asset_class = AssetClass.KR_STOCK

    def __init__(self, live: bool) -> None:
        settings = get_settings()
        self._live = live
        creds = KISCredentials(
            app_key=settings.kis_live_app_key if live else settings.kis_paper_app_key,
            app_secret=settings.kis_live_app_secret if live else settings.kis_paper_app_secret,
            base_url=settings.kis_live_base_url if live else settings.kis_paper_base_url,
            account_no=settings.kis_live_account_no if live else settings.kis_paper_account_no,
        )
        self._creds = creds
        self._auth = KISAuth(creds, mode_key="live" if live else "paper")
        self._http = httpx.AsyncClient(base_url=creds.base_url, timeout=5.0)

    async def place_order(self, order: OrderRequest) -> OrderResult:
        # TODO: POST /uapi/domestic-stock/v1/trading/order-cash
        # TR_ID: 실전 매수 TTTC0802U / 모의 매수 VTTC0802U (매도는 0801)
        raise NotImplementedError

    async def cancel_order(self, broker_order_id: str) -> OrderResult:
        # TODO: POST /uapi/domestic-stock/v1/trading/order-rvsecncl
        raise NotImplementedError

    async def get_balance(self) -> Balance:
        # TODO: GET /uapi/domestic-stock/v1/trading/inquire-balance
        raise NotImplementedError
