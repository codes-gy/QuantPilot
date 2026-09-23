"""주문 체결/거부, kill-switch 발동, 전략 오류 등 중요 이벤트 알림 발송.

NotificationChannel 포트 목록에만 의존한다 — 등록된 모든 채널로 동시에 발송한다.
"""

from app.features.notification.ports import NotificationChannel


class NotificationService:
    def __init__(self, channels: list[NotificationChannel]) -> None:
        self._channels = channels

    async def notify(self, event_type: str, message: str) -> None:
        for channel in self._channels:
            await channel.send(event_type, message)
