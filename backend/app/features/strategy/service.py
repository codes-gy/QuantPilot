"""전략 애플리케이션 서비스 — StrategyRepository 포트에만 의존한다."""

from app.core.exceptions import QuantPilotError
from app.features.broker.base import AssetClass
from app.features.strategy.engine import validate_rule
from app.features.strategy.models import Strategy, StrategyStatus
from app.features.strategy.ports import StrategyRepository
from app.features.strategy.schemas import StrategyCreate


class StrategyNotFoundError(QuantPilotError):
    """요청한 전략이 없음."""


class InvalidStrategyError(QuantPilotError):
    """전략 설정이 실행할 수 없는 상태라 켤 수 없음."""


class StrategyActiveError(QuantPilotError):
    """실행 중인 전략은 수정/삭제할 수 없음 — 먼저 꺼야 한다."""


def validate_runnable(strategy: Strategy) -> None:
    """러너가 실제로 실행할 수 있는 설정인지 확인한다 (켜기 직전에 호출)."""
    problems: list[str] = []
    try:
        asset_class = AssetClass(strategy.asset_class)
    except ValueError:
        problems.append(f"알 수 없는 자산군: {strategy.asset_class}")
    else:
        if asset_class is AssetClass.CRYPTO and not strategy.symbol.startswith("KRW-"):
            problems.append("코인은 원화 마켓(KRW-*) 심볼만 지원합니다.")
        if asset_class is AssetClass.KR_STOCK and not (strategy.symbol.isdigit() and len(strategy.symbol) == 6):
            problems.append("국내 주식 심볼은 6자리 종목코드여야 합니다.")
    if not strategy.entry_rule:
        problems.append("매수 규칙(entry_rule)이 없습니다.")
    for label, rule in (("매수", strategy.entry_rule), ("매도", strategy.exit_rule)):
        if rule:
            try:
                validate_rule(rule)
            except ValueError as exc:
                problems.append(f"{label} 규칙 오류: {exc}")
    if strategy.max_position_size <= 0:
        problems.append("최대 수량(max_position_size)은 0보다 커야 합니다.")
    if not 0 < strategy.stop_loss_pct < 1:
        problems.append("손절 비율(stop_loss_pct)은 0과 1 사이여야 합니다 (예: 0.03 = 3%).")
    if problems:
        raise InvalidStrategyError(" / ".join(problems))


class StrategyService:
    def __init__(self, strategies: StrategyRepository) -> None:
        self._strategies = strategies

    async def create_strategy(self, payload: StrategyCreate) -> Strategy:
        strategy = Strategy(**payload.model_dump())
        return await self._strategies.add(strategy)

    async def list_strategies(self) -> list[Strategy]:
        return await self._strategies.list_all()

    async def _get_paused(self, strategy_id: int, action: str) -> Strategy:
        """수정/삭제 대상 조회. 실행 중인 전략을 바로 바꾸면 매매 도중 조건이 갑자기 바뀌거나
        감시 중이던 전략이 사라지므로, 꺼진 전략만 허용한다.
        """
        strategy = await self._strategies.get(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(f"strategy {strategy_id} not found")
        if strategy.status == StrategyStatus.ACTIVE:
            raise StrategyActiveError(f"실행 중인 전략은 {action}할 수 없어요. 먼저 꺼 주세요.")
        return strategy

    async def update_strategy(self, strategy_id: int, payload: StrategyCreate) -> Strategy:
        strategy = await self._get_paused(strategy_id, "수정")
        for field, value in payload.model_dump().items():
            setattr(strategy, field, value)
        return await self._strategies.update(strategy)

    async def delete_strategy(self, strategy_id: int) -> None:
        strategy = await self._get_paused(strategy_id, "삭제")
        await self._strategies.delete(strategy)

    async def set_status(self, strategy_id: int, status: StrategyStatus) -> Strategy:
        """전략을 켜거나(active) 끈다(paused). 켤 때만 설정 검증을 한다 — 끄는 것은
        잘못된 설정이라도 항상 허용되어야 하는 안전 동작이다.
        """
        strategy = await self._strategies.get(strategy_id)
        if strategy is None:
            raise StrategyNotFoundError(f"strategy {strategy_id} not found")
        if status is StrategyStatus.ACTIVE:
            validate_runnable(strategy)
        strategy.status = status
        return await self._strategies.update(strategy)
