"""활성 알림 채널을 조립하는 단일 진입점.

새 채널(이메일, 텔레그램 등)을 추가할 때는 이 리스트에 어댑터 인스턴스를
추가하기만 하면 되고, 호출부(risk.guard, trading.tasks 등)는 수정할 필요가 없다.
"""

from app.features.notification.service import NotificationService
from app.features.notification.ws_channel import AppWebSocketChannel


def get_notification_service() -> NotificationService:
    return NotificationService(channels=[AppWebSocketChannel()])
