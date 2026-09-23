from enum import StrEnum
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(StrEnum):
    PAPER = "paper"
    LIVE = "live"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    secret_key: str = "change-me"

    database_url: str
    redis_url: str

    celery_broker_url: str
    celery_result_backend: str

    # 실전/모의 전환 스위치. 기본값은 반드시 paper — live는 배포 설정에서만 명시적으로 켠다.
    trading_mode: TradingMode = TradingMode.PAPER
    kill_switch_default: bool = False

    # 오늘 실현손익이 이 금액(원)만큼 손실을 넘으면 kill switch를 자동으로 발동한다.
    # None이면 비활성화 (전략별 stop_loss_pct와는 별개의 계좌 전체 서킷브레이커).
    daily_loss_limit_krw: float | None = None

    kis_paper_app_key: str = ""
    kis_paper_app_secret: str = ""
    kis_paper_account_no: str = ""
    kis_paper_base_url: str = ""
    kis_paper_ws_url: str = ""

    kis_live_app_key: str = ""
    kis_live_app_secret: str = ""
    kis_live_account_no: str = ""
    kis_live_base_url: str = ""
    kis_live_ws_url: str = ""

    upbit_access_key: str = ""
    upbit_secret_key: str = ""

    @property
    def is_live_trading(self) -> bool:
        return self.trading_mode is TradingMode.LIVE


@lru_cache
def get_settings() -> Settings:
    return Settings()
