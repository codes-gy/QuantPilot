from enum import StrEnum
from functools import lru_cache

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

    def assert_safe_to_start(self) -> None:
        """실전(live) 모드로 기동하기 직전 마지막 안전 점검.

        기본 시크릿 키나 빈 KIS 실전 자격증명으로 실수로 라이브 모드가 켜지는 것을
        막기 위한 것이다. paper 모드에서는 아무 것도 검사하지 않는다 — 개발 중에는
        자격증명이 비어 있어도 정상적으로 기동되어야 하기 때문이다.
        """
        if not self.is_live_trading:
            return

        problems: list[str] = []
        if self.secret_key == "change-me":
            problems.append("SECRET_KEY가 기본값(change-me)입니다. 실전 배포용 값으로 반드시 교체하세요.")

        required_live_fields = {
            "KIS_LIVE_APP_KEY": self.kis_live_app_key,
            "KIS_LIVE_APP_SECRET": self.kis_live_app_secret,
            "KIS_LIVE_ACCOUNT_NO": self.kis_live_account_no,
            "KIS_LIVE_BASE_URL": self.kis_live_base_url,
            "KIS_LIVE_WS_URL": self.kis_live_ws_url,
        }
        missing = [name for name, value in required_live_fields.items() if not value]
        if missing:
            problems.append(f"TRADING_MODE=live인데 아래 환경변수가 비어 있습니다: {', '.join(missing)}")

        if problems:
            raise RuntimeError(
                "실전 매매 모드 기동을 거부합니다:\n- " + "\n- ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()
