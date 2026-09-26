"""RiskGuard(모든 주문 제출 경로의 마지막 방어선) 테스트.

kill switch, 손절/포지션 한도, 일일 손실 한도 서킷브레이커가 안전이 중요한
로직인데도 기존에 전혀 테스트되어 있지 않아서 새로 작성했다.
"""

import pytest

from app.core.exceptions import KillSwitchEngagedError, RiskLimitExceededError
from app.features.risk.guard import RiskGuard


async def test_assert_can_trade_passes_when_kill_switch_not_engaged(kill_switch, notifier):
    guard = RiskGuard(kill_switch=kill_switch, notifier=notifier)

    await guard.assert_can_trade()  # 예외 없이 통과해야 한다


async def test_assert_can_trade_blocks_when_kill_switch_engaged(kill_switch, notifier):
    guard = RiskGuard(kill_switch=kill_switch, notifier=notifier)
    await kill_switch.engage()

    with pytest.raises(KillSwitchEngagedError):
        await guard.assert_can_trade()


async def test_engage_kill_switch_persists_state_and_notifies(kill_switch, notifier):
    guard = RiskGuard(kill_switch=kill_switch, notifier=notifier)

    await guard.engage_kill_switch("테스트 사유")

    assert await kill_switch.is_engaged() is True
    assert notifier.events == [("kill_switch_engaged", "테스트 사유")]


async def test_release_kill_switch_clears_state(kill_switch, notifier):
    guard = RiskGuard(kill_switch=kill_switch, notifier=notifier)
    await kill_switch.engage()

    await guard.release_kill_switch()

    assert await kill_switch.is_engaged() is False


async def test_check_stop_loss_raises_when_loss_exceeds_threshold(kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)

    with pytest.raises(RiskLimitExceededError):
        await guard.check_stop_loss(symbol="TEST", entry_price=1000, current_price=940, stop_loss_pct=0.05)


async def test_check_stop_loss_passes_when_within_threshold(kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)

    await guard.check_stop_loss(symbol="TEST", entry_price=1000, current_price=980, stop_loss_pct=0.05)


async def test_check_position_size_raises_when_over_limit(kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)

    with pytest.raises(RiskLimitExceededError):
        await guard.check_position_size(requested_qty=20, max_position_size=10)


async def test_check_position_size_passes_when_within_limit(kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)

    await guard.check_position_size(requested_qty=5, max_position_size=10)


async def test_record_fill_pnl_accumulates_without_engaging_when_limit_not_set(kill_switch, daily_pnl):
    guard = RiskGuard(kill_switch=kill_switch, daily_pnl=daily_pnl, daily_loss_limit_krw=None)

    await guard.record_fill_pnl(-50_000)

    assert await guard.get_today_realized_pnl() == -50_000
    assert await kill_switch.is_engaged() is False  # 한도 미설정이면 절대 발동되면 안 됨


async def test_record_fill_pnl_engages_kill_switch_when_daily_limit_exceeded(kill_switch, daily_pnl, notifier):
    guard = RiskGuard(
        kill_switch=kill_switch,
        notifier=notifier,
        daily_pnl=daily_pnl,
        daily_loss_limit_krw=100_000,
    )

    await guard.record_fill_pnl(-60_000)
    assert await kill_switch.is_engaged() is False  # 아직 한도 미달 (-60,000 > -100,000)

    await guard.record_fill_pnl(-50_000)  # 누적 -110,000 -> 한도(-100,000) 초과
    assert await kill_switch.is_engaged() is True
    assert notifier.events[-1][0] == "kill_switch_engaged"


async def test_record_fill_pnl_does_not_double_notify_once_already_engaged(kill_switch, daily_pnl, notifier):
    guard = RiskGuard(
        kill_switch=kill_switch,
        notifier=notifier,
        daily_pnl=daily_pnl,
        daily_loss_limit_krw=100_000,
    )

    await guard.record_fill_pnl(-150_000)  # 한 번에 한도 초과
    assert len(notifier.events) == 1

    await guard.record_fill_pnl(-10_000)  # 이미 발동된 상태 -> 중복 알림이 없어야 한다
    assert len(notifier.events) == 1


async def test_record_fill_pnl_is_noop_without_daily_pnl_repository(kill_switch):
    """daily_pnl을 주입하지 않은 경우(선택적 의존성) 조용히 아무 일도 하지 않아야 한다."""
    guard = RiskGuard(kill_switch=kill_switch, daily_loss_limit_krw=100_000)

    await guard.record_fill_pnl(-1_000_000)  # 예외 없이 통과해야 함

    assert await guard.get_today_realized_pnl() == 0.0
    assert await kill_switch.is_engaged() is False
