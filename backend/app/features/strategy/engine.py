"""전략 조건 평가 엔진. 순수 함수에 가깝게 유지해 단위테스트/백테스트에서 재사용한다.

새로운 규칙 타입을 추가할 때는 _RULE_HANDLERS에 등록만 하면 되고, runner.py/trading
쪽 코드는 수정할 필요가 없다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum


class Signal(StrEnum):
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    price: float
    price_history: list[float]  # 최근 N개 가격 (이동평균 등 계산용)


RuleHandler = Callable[[dict, MarketSnapshot], bool]


def _ma_cross(rule: dict, snapshot: MarketSnapshot) -> bool:
    fast, slow = rule["fast"], rule["slow"]
    if len(snapshot.price_history) < slow:
        return False
    fast_ma = sum(snapshot.price_history[-fast:]) / fast
    slow_ma = sum(snapshot.price_history[-slow:]) / slow
    return fast_ma > slow_ma


def _price_threshold(rule: dict, snapshot: MarketSnapshot) -> bool:
    return snapshot.price <= rule["below"] if "below" in rule else snapshot.price >= rule["above"]


_RULE_HANDLERS: dict[str, RuleHandler] = {
    "ma_cross": _ma_cross,
    "price_threshold": _price_threshold,
}


def validate_rule(rule: dict) -> None:
    """전략을 켜기 전에 규칙이 엔진에서 실제로 평가 가능한지 확인한다. 잘못된 규칙으로
    켜지면 러너가 틱마다 예외를 내며 그 전략을 평가하지 못하므로 미리 막는다.
    """
    rule_type = rule.get("type")
    if rule_type not in _RULE_HANDLERS:
        raise ValueError(f"지원하지 않는 규칙 타입: {rule_type!r} (가능: {', '.join(_RULE_HANDLERS)})")
    if rule_type == "ma_cross":
        fast, slow = rule.get("fast"), rule.get("slow")
        if not (isinstance(fast, int) and isinstance(slow, int) and 0 < fast < slow):
            raise ValueError("ma_cross는 0 < fast < slow 인 정수 fast/slow가 필요합니다.")
    if rule_type == "price_threshold":
        keys = [k for k in ("below", "above") if k in rule]
        if len(keys) != 1 or not isinstance(rule[keys[0]], (int, float)) or rule[keys[0]] <= 0:
            raise ValueError("price_threshold는 양수 below 또는 above 중 하나만 가져야 합니다.")


def evaluate_entry(entry_rule: dict, snapshot: MarketSnapshot) -> Signal:
    handler = _RULE_HANDLERS.get(entry_rule["type"])
    if handler is None:
        raise ValueError(f"unknown rule type: {entry_rule['type']}")
    return Signal.BUY if handler(entry_rule, snapshot) else Signal.HOLD


def evaluate_exit(exit_rule: dict, snapshot: MarketSnapshot) -> Signal:
    handler = _RULE_HANDLERS.get(exit_rule["type"])
    if handler is None:
        raise ValueError(f"unknown rule type: {exit_rule['type']}")
    return Signal.SELL if handler(exit_rule, snapshot) else Signal.HOLD
