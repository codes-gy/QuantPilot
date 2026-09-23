import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.security import decode_access_token
from app.ws.manager import ws_manager

router = APIRouter()


@router.websocket("/ws/live")
async def live_updates(ws: WebSocket, token: str) -> None:
    """토큰은 쿼리 파라미터로 전달한다: /ws/live?token=<access_token>

    WebSocket 핸드셰이크는 브라우저/Flutter 클라이언트에서 커스텀 헤더를 붙이기
    까다로워, REST와 동일한 JWT를 쿼리 파라미터로 받는 방식이 일반적이다.
    FastAPI는 필수 쿼리 파라미터 검증 실패 시 연결을 자동으로 거부(403)한다.
    """
    try:
        decode_access_token(token)
    except jwt.PyJWTError:
        await ws.close(code=4401)
        return

    await ws_manager.connect(ws)
    try:
        while True:
            await ws.receive_text()  # 클라이언트 구독 변경 메시지 등 (필요 시 파싱)
    except WebSocketDisconnect:
        await ws_manager.disconnect(ws)
