import asyncio

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.exceptions import BrokerAPIError
from app.core.logging import get_logger
from app.features.broker.kis.auth import KISAuth, KISCredentials

logger = get_logger(__name__)


@celery_app.task
def refresh_kis_token() -> None:
    """paper/live 토큰을 모두 갱신해 Redis 캐시를 채워둔다 (celery-beat, 6시간마다)."""
    settings = get_settings()
    for mode_key, live in (("paper", False), ("live", True)):
        creds = KISCredentials(
            app_key=settings.kis_live_app_key if live else settings.kis_paper_app_key,
            app_secret=settings.kis_live_app_secret if live else settings.kis_paper_app_secret,
            base_url=settings.kis_live_base_url if live else settings.kis_paper_base_url,
            account_no=settings.kis_live_account_no if live else settings.kis_paper_account_no,
        )
        if not creds.app_key:
            continue  # 해당 모드 자격증명 미설정 시 skip

        try:
            asyncio.run(KISAuth(creds, mode_key).refresh_token())
        except BrokerAPIError:
            logger.exception("KIS token refresh failed (%s)", mode_key)
