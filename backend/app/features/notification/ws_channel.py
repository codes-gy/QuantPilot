"""NotificationChannel 포트의 앱 WebSocket 구현체.

MVP에서는 이 채널 하나만 등록한다. 이메일/텔레그램을 추가할 때는 이 파일과 같은
레벨에 NotificationChannel을 구현하는 어댑터를 하나 더 만들고, 조립 지점(service.py의
default_channels)에 등록하기만 하면 된다 — 호출부(risk.guard 등)는 수정할 필요가 없다.
"""

from app.core.logging import get_logger
from app.features.notification.ports import NotificationChannel
from app.ws.manager import ws_manager

logger = get_logger(__name__)


class AppWebSocketChannel(NotificationChannel):
    async def send(self, event_type: str, message: str) -> None:
        await ws_manager.broadcast({"type": event_type, "message": message})
        logger.info("notification sent: %s - %s", event_type, message)
