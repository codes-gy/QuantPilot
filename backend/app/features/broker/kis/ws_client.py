"""KIS 실시간 시세 WebSocket 클라이언트 (H0STCNT0: 국내주식 실시간 체결가).

market_data/ingestor.py 가 이 어댑터를 장시간 구동하며 수신한 Tick을
market_data/redis_cache.py 를 통해 Redis에 반영한다.

재연결/백오프는 이 클래스가 아니라 호출부(ingestor._run_feed)가 담당한다 — 이미 그
쪽에 지수 백오프 없는 3초 재시도 루프가 있어, 여기서 또 재연결 로직을 넣으면 두 계층이
서로 다른 정책으로 경쟁하게 된다. 이 클래스는 "연결 1회 = subscribe() 호출 1회"로
단순하게 유지하고, 연결이 끊기면 예외를 그대로 올려 호출부가 재시도하게 한다.
"""

import json
import time
from collections.abc import AsyncIterator

import websockets

from app.core.exceptions import BrokerAPIError
from app.core.logging import get_logger
from app.features.broker.base import AssetClass, MarketDataAdapter, Tick
from app.features.broker.kis.auth import KISAuth

logger = get_logger(__name__)

_TR_ID = "H0STCNT0"
_FIELD_COUNT = 46  # 실시간체결가 응답 레코드 1건당 필드 수 (KIS 실시간 국내주식 체결가 스펙)
_SYMBOL_IDX = 0  # 유가증권단축종목코드
_PRICE_IDX = 2  # 주식현재가
_VOLUME_IDX = 12  # 체결거래량


class KISMarketDataAdapter(MarketDataAdapter):
    asset_class = AssetClass.KR_STOCK

    def __init__(self, auth: KISAuth, ws_url: str) -> None:
        self._auth = auth
        self._ws_url = ws_url

    async def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]:
        if not symbols:
            return

        approval_key = await self._auth.get_approval_key()

        async with websockets.connect(self._ws_url, ping_interval=None) as ws:
            for symbol in symbols:
                await ws.send(
                    json.dumps(
                        {
                            "header": {
                                "approval_key": approval_key,
                                "custtype": "P",
                                "tr_type": "1",
                                "content-type": "utf-8",
                            },
                            "body": {"input": {"tr_id": _TR_ID, "tr_key": symbol}},
                        }
                    )
                )

            async for raw in ws:
                # KIS 프로토콜: 앞 1글자가 '0'|'1'이면 실시간 데이터(파이프 구분),
                # 그 외(JSON)는 구독 응답/PINGPONG 등 제어 메시지.
                if raw and raw[0] in ("0", "1"):
                    for tick in self._parse_realtime_frame(raw):
                        yield tick
                    continue

                try:
                    message = json.loads(raw)
                except ValueError:
                    logger.warning("unparseable KIS control message: %s", raw[:200])
                    continue

                header = message.get("header", {})
                if header.get("tr_id") == "PINGPONG":
                    await ws.send(raw)  # 받은 그대로 echo해야 연결이 유지된다.
                    continue

                body = message.get("body", {})
                if body.get("rt_cd") not in (None, "0"):
                    # 구독 자체가 거부된 경우 — 예: 잘못된 종목코드, 세션 만료
                    raise BrokerAPIError(f"KIS subscribe rejected: {body.get('msg1')}")

    @staticmethod
    def _parse_realtime_frame(raw: str) -> list[Tick]:
        parts = raw.split("|")
        if len(parts) < 4:
            return []
        _encrypted_flag, tr_id, data_cnt, data_str = parts[0], parts[1], parts[2], parts[3]
        if tr_id != _TR_ID:
            return []

        fields = data_str.split("^")
        try:
            count = int(data_cnt)
        except ValueError:
            count = 1

        now = time.time()  # 서버 수신 시각 — 필드상의 주식체결시간(HHMMSS)은 참고용으로만 존재
        ticks: list[Tick] = []
        for i in range(count):
            record = fields[i * _FIELD_COUNT : (i + 1) * _FIELD_COUNT]
            if len(record) < _FIELD_COUNT:
                break
            try:
                ticks.append(
                    Tick(
                        symbol=record[_SYMBOL_IDX],
                        price=float(record[_PRICE_IDX]),
                        volume=float(record[_VOLUME_IDX]),
                        timestamp=now,
                    )
                )
            except ValueError:
                logger.warning("malformed KIS realtime record: %s", record)
        return ticks
