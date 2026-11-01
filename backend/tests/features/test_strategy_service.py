import pytest

from app.features.strategy.models import Strategy, StrategyStatus
from app.features.strategy.ports import StrategyRepository
from app.features.strategy.schemas import StrategyCreate
from app.features.strategy.service import (
    InvalidStrategyError,
    StrategyActiveError,
    StrategyNotFoundError,
    StrategyService,
)


class InMemoryStrategyRepository(StrategyRepository):
    def __init__(self, strategies: list[Strategy]) -> None:
        self._items = {s.id: s for s in strategies}

    async def add(self, strategy: Strategy) -> Strategy:
        self._items[strategy.id] = strategy
        return strategy

    async def list_all(self) -> list[Strategy]:
        return list(self._items.values())

    async def list_active(self) -> list[Strategy]:
        return [s for s in self._items.values() if s.status == StrategyStatus.ACTIVE]

    async def get(self, strategy_id: int) -> Strategy | None:
        return self._items.get(strategy_id)

    async def update(self, strategy: Strategy) -> Strategy:
        return strategy

    async def delete(self, strategy: Strategy) -> None:
        del self._items[strategy.id]


def _strategy(**overrides) -> Strategy:
    fields = dict(
        id=1,
        name="test",
        asset_class="kr_stock",
        symbol="005930",
        status=StrategyStatus.PAUSED,
        entry_rule={"type": "price_threshold", "below": 7000},
        exit_rule={"type": "price_threshold", "above": 7500},
        max_position_size=1,
        stop_loss_pct=0.03,
    )
    fields.update(overrides)
    return Strategy(**fields)


async def test_activate_and_pause():
    repo = InMemoryStrategyRepository([_strategy()])
    service = StrategyService(repo)

    activated = await service.set_status(1, StrategyStatus.ACTIVE)
    assert activated.status == StrategyStatus.ACTIVE
    assert [s.id for s in await repo.list_active()] == [1]

    paused = await service.set_status(1, StrategyStatus.PAUSED)
    assert paused.status == StrategyStatus.PAUSED
    assert await repo.list_active() == []


async def test_missing_strategy_raises_not_found():
    service = StrategyService(InMemoryStrategyRepository([]))
    with pytest.raises(StrategyNotFoundError):
        await service.set_status(99, StrategyStatus.ACTIVE)


@pytest.mark.parametrize(
    "overrides",
    [
        {"entry_rule": {"type": "unknown"}},
        {"entry_rule": {}},
        {"exit_rule": {"type": "ma_cross", "fast": 20, "slow": 5}},
        {"entry_rule": {"type": "price_threshold", "below": 7000, "above": 8000}},
        {"max_position_size": 0},
        {"stop_loss_pct": 3},  # 3%를 0.03 대신 3으로 넣는 실수
        {"asset_class": "crypto", "symbol": "BTC-ETH"},
        {"asset_class": "kr_stock", "symbol": "KRW-BTC"},
        {"asset_class": "fx"},
    ],
)
async def test_invalid_strategy_cannot_be_activated(overrides):
    repo = InMemoryStrategyRepository([_strategy(**overrides)])
    with pytest.raises(InvalidStrategyError):
        await StrategyService(repo).set_status(1, StrategyStatus.ACTIVE)
    assert await repo.list_active() == []


async def test_invalid_strategy_can_still_be_paused():
    # 끄기는 안전 동작이라 설정이 잘못돼 있어도 항상 허용돼야 한다.
    repo = InMemoryStrategyRepository([_strategy(status=StrategyStatus.ACTIVE, max_position_size=0)])
    paused = await StrategyService(repo).set_status(1, StrategyStatus.PAUSED)
    assert paused.status == StrategyStatus.PAUSED


async def test_alphanumeric_stock_code_is_valid():
    # 2024년 이후 신규 상장 종목코드 (예: 0001A0 덕양에너젠)
    repo = InMemoryStrategyRepository([_strategy(symbol="0001A0")])
    activated = await StrategyService(repo).set_status(1, StrategyStatus.ACTIVE)
    assert activated.status == StrategyStatus.ACTIVE


async def test_crypto_strategy_with_krw_market_is_valid():
    repo = InMemoryStrategyRepository(
        [_strategy(asset_class="crypto", symbol="KRW-BTC", max_position_size=0.0001)]
    )
    activated = await StrategyService(repo).set_status(1, StrategyStatus.ACTIVE)
    assert activated.status == StrategyStatus.ACTIVE


def _payload(**overrides) -> StrategyCreate:
    fields = dict(
        name="수정됨",
        asset_class="crypto",
        symbol="KRW-BTC",
        entry_rule={"type": "price_threshold", "below": 100_000_000},
        exit_rule={},
        max_position_size=0.0001,
        stop_loss_pct=0.05,
    )
    fields.update(overrides)
    return StrategyCreate(**fields)


async def test_update_paused_strategy_replaces_settings_and_stays_paused():
    repo = InMemoryStrategyRepository([_strategy()])
    updated = await StrategyService(repo).update_strategy(1, _payload())

    assert updated.name == "수정됨"
    assert updated.asset_class == "crypto"
    assert updated.symbol == "KRW-BTC"
    assert updated.exit_rule == {}
    assert updated.stop_loss_pct == 0.05
    assert updated.status == StrategyStatus.PAUSED


async def test_active_strategy_cannot_be_updated_or_deleted():
    repo = InMemoryStrategyRepository([_strategy(status=StrategyStatus.ACTIVE)])
    service = StrategyService(repo)

    with pytest.raises(StrategyActiveError):
        await service.update_strategy(1, _payload())
    with pytest.raises(StrategyActiveError):
        await service.delete_strategy(1)

    unchanged = await repo.get(1)
    assert unchanged is not None and unchanged.name == "test"


async def test_delete_paused_strategy():
    repo = InMemoryStrategyRepository([_strategy()])
    await StrategyService(repo).delete_strategy(1)
    assert await repo.list_all() == []


async def test_update_or_delete_missing_strategy_raises_not_found():
    service = StrategyService(InMemoryStrategyRepository([]))
    with pytest.raises(StrategyNotFoundError):
        await service.update_strategy(1, _payload())
    with pytest.raises(StrategyNotFoundError):
        await service.delete_strategy(1)
