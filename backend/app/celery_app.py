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
}
celery_app.conf.timezone = "Asia/Seoul"
