"""Upbit 실시간 시세 WebSocket 클라이언트 (wss://api.upbit.com/websocket/v1, type=trade).

인증 없이 공개 체결 시세를 바로 구독할 수 있다. 재연결/백오프는 KIS 어댑터와 마찬가지로
이 클래스가 아니라 호출부(market_data/ingestor._run_feed)가 담당한다 — 이 클래스는
"연결 1회 = subscribe() 호출 1회"로 단순하게 유지하고, 끊기면 예외를 그대로 올린다.

Upbit은 일정 시간 메시지가 없으면 연결을 끊으므로 websockets 기본 ping(20초)을 유지한다.
"""

import json
import uuid
from collections.abc import AsyncIterator

import websockets

from app.core.exceptions import BrokerAPIError
from app.core.logging import get_logger
from app.features.broker.base import AssetClass, MarketDataAdapter, Tick

logger = get_logger(__name__)

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


class UpbitMarketDataAdapter(MarketDataAdapter):
    asset_class = AssetClass.CRYPTO

    def __init__(self, ws_url: str = UPBIT_WS_URL) -> None:
        self._ws_url = ws_url

    async def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]:
        if not symbols:
            return

        request = [
            {"ticket": str(uuid.uuid4())},
            {"type": "trade", "codes": [s.upper() for s in symbols]},
            {"format": "DEFAULT"},
        ]
        async with websockets.connect(self._ws_url) as ws:
            await ws.send(json.dumps(request))
            async for raw in ws:
                tick = self.parse_message(raw)
                if tick is not None:
                    yield tick

    @staticmethod
    def parse_message(raw: str | bytes) -> Tick | None:
        """Upbit은 시세를 바이너리 프레임(UTF-8 JSON)으로 보낸다."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            message = json.loads(raw)
        except ValueError:
            logger.warning("unparseable Upbit message: %s", raw[:200])
            return None

        if "error" in message:
            raise BrokerAPIError(f"Upbit subscribe rejected: {message['error']}")
        if message.get("type") != "trade":
            return None  # {"status": "UP"} 등 제어 메시지

        try:
            return Tick(
                symbol=message["code"],
                price=float(message["trade_price"]),
                volume=float(message["trade_volume"]),
                timestamp=float(message["trade_timestamp"]) / 1000,
            )
        except (KeyError, TypeError, ValueError):
            logger.warning("malformed Upbit trade message: %s", message)
            return None
