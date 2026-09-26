from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "quantpilot",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.features.trading.tasks", "app.features.broker.kis.tasks"],
)

celery_app.conf.beat_schedule = {
    # KIS 접근토큰은 24시간 만료 — 여유를 두고 매 6시간마다 갱신
    "refresh-kis-token": {
        "task": "app.features.broker.kis.tasks.refresh_kis_token",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # KIS order-cash 응답은 접수 확인뿐이라 체결 여부를 별도로 확인해야 한다.
    # 전략 재평가 주기(30초)보다 짧게 잡아, 체결 확인이 다음 전략 판단에 늦지 않게 한다.
    "poll-pending-order-fills": {
        "task": "app.features.trading.tasks.poll_pending_order_fills",
        "schedule": 10.0,  # 초 단위
    },
}
celery_app.conf.timezone = "Asia/Seoul"
