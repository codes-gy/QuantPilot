"""주문 체결/거부, kill-switch 발동, 전략 오류 등 중요 이벤트 알림 발송.

MVP에서는 channels.py의 push(app WebSocket)만 구현하고, 추후 이메일/슬랙 채널을 추가한다.
"""

from app.features.notification.channels import push_to_app


async def notify(event_type: str, message: str) -> None:
    await push_to_app(event_type, message)
