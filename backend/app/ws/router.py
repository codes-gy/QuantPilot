from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.ws.manager import ws_manager

router = APIRouter()


@router.websocket("/ws/live")
async def live_updates(ws: WebSocket) -> None:
    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # 클라이언트 구독 변경 메시지 등 (필요 시 파싱)
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
