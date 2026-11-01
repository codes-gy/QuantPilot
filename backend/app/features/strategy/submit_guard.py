"""전략 러너가 같은 신호로 주문을 반복 제출하지 않도록 막는 순수 로직 (시각은 호출부가 넘긴다).

1. 제출 간격(쿨다운) — 방향별로 따로 둔다.
   - 매수: 마지막 매수 제출 후 BUY_COOLDOWN_SECONDS 동안 재매수 금지. 제출(delay) 후 워커가
     주문을 DB에 기록하기 전까지는 미체결 주문 조회(has_open_order)에 잡히지 않으므로,
     그 사이 틱마다 매수가 연달아 나가지 않게 막는다.
   - 매도: SELL_COOLDOWN_SECONDS로 짧게 둔다. 손절/익절은 늦을수록 손해이므로 매수 쿨다운에
     묶이면 안 된다 (예전에는 전략 단위 60초 하나라 매수 직후 급락해도 손절이 최대 60초 늦었다).
     짧게라도 두는 이유는 위와 같은 기록 지연 동안 같은 매도가 중복 제출되는 것을 막기 위해서다.
2. 재진입 대기(re-arm) — 매도 후에는 매수 조건이 한 번 거짓이 됐다가 다시 참이 될 때만 재매수.
   "X원 이하 매수" 전략이 손절로 팔면 가격은 이미 X원 아래라 매수 조건이 계속 참이다.
   이걸 막지 않으면 손절 -> 즉시 재매수 -> 손절이 반복되며 수수료와 손실이 쌓인다.

상태는 러너 프로세스 메모리에만 있다 — 러너가 재시작되면 초기화된다.
"""

from dataclasses import dataclass, field

from app.features.strategy.engine import Signal

BUY_COOLDOWN_SECONDS = 60.0
SELL_COOLDOWN_SECONDS = 15.0


@dataclass
class SubmitGuard:
    _last_submitted: dict[tuple[int, Signal], float] = field(default_factory=dict)
    _awaiting_rearm: set[int] = field(default_factory=set)

    def entry_evaluated(self, strategy_id: int, entry_signal: Signal) -> None:
        """포지션이 없을 때 매수 조건을 평가할 때마다 호출. 조건이 거짓(HOLD)이면 재진입 허용."""
        if entry_signal is Signal.HOLD:
            self._awaiting_rearm.discard(strategy_id)

    def allows(self, strategy_id: int, signal: Signal, now: float) -> bool:
        if signal is Signal.BUY and strategy_id in self._awaiting_rearm:
            return False
        last = self._last_submitted.get((strategy_id, signal))
        cooldown = BUY_COOLDOWN_SECONDS if signal is Signal.BUY else SELL_COOLDOWN_SECONDS
        return last is None or now - last >= cooldown

    def record(self, strategy_id: int, signal: Signal, now: float) -> None:
        self._last_submitted[(strategy_id, signal)] = now
        if signal is Signal.SELL:
            self._awaiting_rearm.add(strategy_id)
