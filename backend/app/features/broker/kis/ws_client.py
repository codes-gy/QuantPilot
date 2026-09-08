"""KIS 실시간 시세 WebSocket 클라이언트 (H0STCNT0: 국내주식 실시간 체결가).

market_data/ingestor.py 가 이 어댑터를 장시간 구동하며 수신한 Tick을
market_data/cache.py 를 통해 Redis에 반영한다.
"""

from collections.abc import AsyncIterator

from app.features.broker.base import AssetClass, MarketDataAdapter, Tick
from app.features.broker.kis.auth import KISAuth


class KISMarketDataAdapter(MarketDataAdapter):
    asset_class = AssetClass.KR_STOCK

    def __init__(self, auth: KISAuth | None = None) -> None:
        self._auth = auth

    async def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]:
        # TODO:
        #  1. approval_key 발급 (KISAuth.get_approval_key)
        #  2. wss 연결 후 종목별 H0STCNT0 구독 프레임 전송
        #  3. 재연결/백오프 로직 (연결 끊김 시 지수 백오프로 재구독)
        #  4. 수신 프레임 파싱 -> Tick 생성 -> yield
        raise NotImplementedError
        yield  # pragma: no cover
