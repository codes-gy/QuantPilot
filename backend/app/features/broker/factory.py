"""모의/실전, 주식/코인 조합에 맞는 어댑터를 조립하는 단일 진입점.

TRADING_MODE(paper/live) 스위치는 반드시 이 팩토리에서만 분기한다 — 다른 어디에서도
KIS_LIVE_* / KIS_PAPER_* 자격증명을 직접 선택하지 않도록 강제해 실수로 실전 주문이
나가는 사고를 막는다.
"""

from app.core.config import TradingMode, get_settings
from app.features.broker.base import AssetClass, BrokerAdapter, MarketDataAdapter
from app.features.broker.kis.auth import KISAuth, KISCredentials
from app.features.broker.kis.client import KISBrokerAdapter
from app.features.broker.kis.ws_client import KISMarketDataAdapter
from app.features.broker.upbit.client import UpbitBrokerAdapter
from app.features.broker.upbit.ws_client import UpbitMarketDataAdapter


def get_broker_adapter(asset_class: AssetClass) -> BrokerAdapter:
    settings = get_settings()
    is_live = settings.trading_mode is TradingMode.LIVE

    if asset_class is AssetClass.KR_STOCK:
        return KISBrokerAdapter(live=is_live)
    if asset_class is AssetClass.CRYPTO:
        return UpbitBrokerAdapter(live=is_live)
    raise ValueError(f"unsupported asset class: {asset_class}")


def get_market_data_adapter(asset_class: AssetClass) -> MarketDataAdapter:
    settings = get_settings()
    is_live = settings.trading_mode is TradingMode.LIVE

    if asset_class is AssetClass.KR_STOCK:
        creds = KISCredentials(
            app_key=settings.kis_live_app_key if is_live else settings.kis_paper_app_key,
            app_secret=settings.kis_live_app_secret if is_live else settings.kis_paper_app_secret,
            base_url=settings.kis_live_base_url if is_live else settings.kis_paper_base_url,
            account_no=settings.kis_live_account_no if is_live else settings.kis_paper_account_no,
        )
        auth = KISAuth(creds, mode_key="live" if is_live else "paper")
        ws_url = settings.kis_live_ws_url if is_live else settings.kis_paper_ws_url
        return KISMarketDataAdapter(auth=auth, ws_url=ws_url)
    if asset_class is AssetClass.CRYPTO:
        return UpbitMarketDataAdapter()
    raise ValueError(f"unsupported asset class: {asset_class}")
