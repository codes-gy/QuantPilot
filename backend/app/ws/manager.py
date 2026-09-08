"""Flutter 앱에 실시간 시세/주문 상태를 릴레이하는 WebSocket 연결 관리자.

KIS/Upbit WebSocket(수집용)과는 별개다 — 백엔드가 팬아웃 허브 역할을 해서
클라이언트는 각자 필요한 심볼만 이 채널로 구독한다.
"""

import asyncio

from fastapi import WebSocket


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._connections.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(ws)

    async def broadcast(self, payload: dict) -> None:
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                await self.disconnect(ws)


ws_manager = ConnectionManager()
