class QuantPilotError(Exception):
    """모든 도메인 예외의 베이스 클래스."""


class KillSwitchEngagedError(QuantPilotError):
    """비상 정지 스위치가 켜져 있어 주문 제출이 차단됨."""


class RiskLimitExceededError(QuantPilotError):
    """손절/최대 손실 한도 등 리스크 가드에 의해 주문이 거부됨."""


class BrokerAPIError(QuantPilotError):
    """증권사 API 호출 실패 (인증, 레이트리밋, 주문 거부 등)."""


class StrategyEvaluationError(QuantPilotError):
    """전략 조건 평가 중 오류."""
