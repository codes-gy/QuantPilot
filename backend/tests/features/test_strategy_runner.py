"""전략 러너의 순수 판단 로직 테스트 (DB/Redis 없이).

- 신규 매수 시 포지션 한도는 "실제 보유 수량 + 이번 주문 수량" 기준으로 확인해야 한다.
  예전에는 check_position_size(max, max)로 호출해 항상 통과했다.
- paper 모드에서는 Upbit이 주문을 받을 수 없으므로 코인 전략을 평가하지 않아야 한다.
"""

from types import SimpleNamespace

from app.features.broker.base import AssetClass
from app.features.risk.guard import RiskGuard
from app.features.strategy.runner import _checked_entry_quantity, _runnable_asset_classes


def _strategy(max_position_size: float = 10):
    return SimpleNamespace(id=1, symbol="005930", max_position_size=max_position_size)


async def test_entry_quantity_with_no_holding_buys_max_position(kill_switch):
    guard = RiskGuard(kill_switch=kill_switch)

    assert await _checked_entry_quantity(_strategy(), 0.0, guard) == 10


async def test_entry_blocked_when_holding_plus_order_exceeds_max(kill_switch):
    """평가 이후 체결이 반영돼 이미 보유 중이면, 같은 수량을 또 사면 한도를 넘는다."""
    guard = RiskGuard(kill_switch=kill_switch)

    assert await _checked_entry_quantity(_strategy(), 3.0, guard) is None


def test_crypto_is_not_evaluated_in_paper_mode():
    assert _runnable_asset_classes(live=False) == [AssetClass.KR_STOCK]


def test_crypto_is_evaluated_in_live_mode():
    assert _runnable_asset_classes(live=True) == [AssetClass.KR_STOCK, AssetClass.CRYPTO]
