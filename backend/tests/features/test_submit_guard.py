from app.features.strategy.engine import Signal
from app.features.strategy.submit_guard import (
    BUY_COOLDOWN_SECONDS,
    SELL_COOLDOWN_SECONDS,
    SubmitGuard,
)


def test_buy_cooldown_blocks_repeated_buys():
    guard = SubmitGuard()
    assert guard.allows(1, Signal.BUY, now=0)
    guard.record(1, Signal.BUY, now=0)

    assert not guard.allows(1, Signal.BUY, now=1)
    assert not guard.allows(1, Signal.BUY, now=BUY_COOLDOWN_SECONDS - 0.1)
    assert guard.allows(1, Signal.BUY, now=BUY_COOLDOWN_SECONDS)


def test_stop_loss_right_after_buy_is_not_blocked_by_buy_cooldown():
    # 예전엔 전략 단위 60초 쿨다운 하나라 매수 직후 급락해도 손절이 최대 60초 늦었다.
    guard = SubmitGuard()
    guard.record(1, Signal.BUY, now=0)
    assert guard.allows(1, Signal.SELL, now=2)


def test_sell_has_short_cooldown_against_duplicate_submission():
    guard = SubmitGuard()
    guard.record(1, Signal.SELL, now=0)
    assert not guard.allows(1, Signal.SELL, now=1)
    assert guard.allows(1, Signal.SELL, now=SELL_COOLDOWN_SECONDS)
    assert SELL_COOLDOWN_SECONDS < BUY_COOLDOWN_SECONDS


def test_no_rebuy_after_sell_until_entry_condition_resets():
    # "7,000원 이하 매수" 전략이 6,790원에서 손절 -> 가격은 여전히 매수 조건을 만족한다.
    guard = SubmitGuard()
    guard.record(1, Signal.SELL, now=0)

    guard.entry_evaluated(1, Signal.BUY)  # 조건 여전히 참
    assert not guard.allows(1, Signal.BUY, now=1000)  # 쿨다운이 지나도 재매수 금지

    guard.entry_evaluated(1, Signal.HOLD)  # 가격이 7,000원 위로 회복 -> 조건 거짓
    guard.entry_evaluated(1, Signal.BUY)  # 다시 7,000원 이하로 -> 새 진입 신호
    assert guard.allows(1, Signal.BUY, now=1001)


def test_strategies_are_independent():
    guard = SubmitGuard()
    guard.record(1, Signal.BUY, now=0)
    guard.record(1, Signal.SELL, now=0)
    assert guard.allows(2, Signal.BUY, now=0)
    assert guard.allows(2, Signal.SELL, now=0)
