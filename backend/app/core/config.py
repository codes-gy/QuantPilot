from enum import StrEnum
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


# 기본 SECRET_KEY를 허용하는 개발용 APP_ENV. 그 밖의 값(production, staging 등)은 거부한다.
_DEV_APP_ENVS = frozenset({"local", "test"})
_DEFAULT_SECRET_KEYS = frozenset({"change-me", ""})


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
    # true면 API/전략 러너가 기동할 때마다 kill switch를 켠 상태로 시작한다 (사람이 직접 해제).
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

    # 브라우저(Flutter 웹)에서 API를 호출할 수 있는 출처. 기본값은 이 PC(localhost)의
    # 아무 포트나 허용 — 외부에 배포할 때는 실제 웹 주소만 허용하도록 바꿀 것.
    cors_allow_origin_regex: str = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

    @property
    def is_live_trading(self) -> bool:
        return self.trading_mode is TradingMode.LIVE

    @property
    def is_dev_env(self) -> bool:
        return self.app_env.strip().lower() in _DEV_APP_ENVS

    def assert_safe_to_start(self) -> None:
        """기동 직전 마지막 안전 점검 (API, 전략 러너, Celery 워커가 모두 호출한다).

        - 개발 환경(APP_ENV=local/test)이 아니면 기본/빈 SECRET_KEY를 거부한다. JWT 서명
          키가 공개된 기본값이면 누구나 로그인 토큰을 위조할 수 있기 때문이다.
        - 실전(live) 모드면 APP_ENV와 상관없이 기본 시크릿과 빈 KIS 실전 자격증명을 거부한다.
        paper 모드 + 개발 환경에서는 아무것도 검사하지 않는다 — 개발 중에는 자격증명이
        비어 있어도 정상적으로 기동되어야 하기 때문이다.
        """
        problems: list[str] = []
        default_secret = self.secret_key.strip() in _DEFAULT_SECRET_KEYS
        if default_secret and (self.is_live_trading or not self.is_dev_env):
            problems.append(
                f"SECRET_KEY가 기본값(change-me)이거나 비어 있습니다 (APP_ENV={self.app_env}). "
                "예: python -c \"import secrets; print(secrets.token_urlsafe(48))\" 로 만든 값으로 교체하세요."
            )

        if not self.is_live_trading:
            if problems:
                raise RuntimeError("기동을 거부합니다:\n- " + "\n- ".join(problems))
            return

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
