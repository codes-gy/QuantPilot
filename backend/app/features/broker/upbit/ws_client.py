"""Upbit 실시간 시세 WebSocket 클라이언트 (wss://api.upbit.com/websocket/v1, type=ticker/trade).

인증 없이 공개 시세를 바로 구독할 수 있어 KIS보다 단순하지만, 연결당 구독 종목 수 제한과
잦은 재연결 요구가 있어 market_data/ingestor.py 에서 동일한 재연결/백오프 정책을 공유한다.
"""

from collections.abc import AsyncIterator

from app.features.broker.base import AssetClass, MarketDataAdapter, Tick

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


class UpbitMarketDataAdapter(MarketDataAdapter):
    asset_class = AssetClass.CRYPTO

    async def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]:
        # TODO:
        #  1. wss 연결 후 [{"ticket": ...}, {"type": "trade", "codes": ["KRW-BTC", ...]}] 전송
        #  2. 바이너리 프레임 수신 -> JSON 디코드 -> Tick 생성 -> yield
        #  3. 재연결/백오프 로직 (KIS 어댑터와 동일 정책)
        raise NotImplementedError
        yield  # pragma: no cover
