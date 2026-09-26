"""Settings.assert_safe_to_start() (live 모드 기동 안전장치) 테스트.

TRADING_MODE=live인데 기본 시크릿 키나 빈 KIS 실전 자격증명으로 실수로
기동되는 것을 막기 위한 안전장치라, 이 검사 자체가 항상 정확히 동작해야 한다.
"""

import pytest

from app.core.config import Settings, TradingMode


def _base_kwargs(**overrides) -> dict:
    defaults = {
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "redis_url": "redis://localhost:6379/0",
        "celery_broker_url": "redis://localhost:6379/1",
        "celery_result_backend": "redis://localhost:6379/2",
    }
    defaults.update(overrides)
    return defaults


def test_paper_mode_skips_all_checks_even_with_default_secret() -> None:
    """개발 중에는 paper 모드로 자격증명 없이 기동되는 게 정상이어야 한다."""
    settings = Settings(trading_mode=TradingMode.PAPER, secret_key="change-me", **_base_kwargs())

    settings.assert_safe_to_start()  # 예외 없이 통과해야 한다


def test_live_mode_rejects_default_secret_key() -> None:
    settings = Settings(
        trading_mode=TradingMode.LIVE,
        secret_key="change-me",
        kis_live_app_key="key",
        kis_live_app_secret="secret",
        kis_live_account_no="12345678-01",
        kis_live_base_url="https://openapi.koreainvestment.com:9443",
        kis_live_ws_url="wss://ops.koreainvestment.com:21000",
        **_base_kwargs(),
    )

    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        settings.assert_safe_to_start()


def test_live_mode_rejects_missing_kis_credentials() -> None:
    settings = Settings(
        trading_mode=TradingMode.LIVE,
        secret_key="a-real-production-secret",
        # 로컬 .env에 실제 KIS 자격증명이 있어도 이 테스트가 영향받지 않도록 명시적으로 비워둔다.
        kis_live_app_key="",
        kis_live_app_secret="",
        kis_live_account_no="",
        kis_live_base_url="",
        kis_live_ws_url="",
        **_base_kwargs(),
    )

    with pytest.raises(RuntimeError, match="KIS_LIVE_APP_KEY"):
        settings.assert_safe_to_start()


def test_live_mode_starts_when_secret_and_credentials_are_all_set() -> None:
    settings = Settings(
        trading_mode=TradingMode.LIVE,
        secret_key="a-real-production-secret",
        kis_live_app_key="key",
        kis_live_app_secret="secret",
        kis_live_account_no="12345678-01",
        kis_live_base_url="https://openapi.koreainvestment.com:9443",
        kis_live_ws_url="wss://ops.koreainvestment.com:21000",
        **_base_kwargs(),
    )

    settings.assert_safe_to_start()  # 예외 없이 통과해야 한다
