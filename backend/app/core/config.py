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
