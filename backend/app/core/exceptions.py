class QuantPilotError(Exception):
    """모든 도메인 예외의 베이스 클래스."""


class KillSwitchEngagedError(QuantPilotError):
    """비상 정지 스위치가 켜져 있어 주문 제출이 차단됨."""


class RiskLimitExceededError(QuantPilotError):
    """손절/최대 손실 한도 등 리스크 가드에 의해 주문이 거부됨."""


class BrokerAPIError(QuantPilotError):
    """증권사 API 호출 실패 (인증, 레이트리밋, 주문 거부 등)."""


class SymbolNotFoundError(QuantPilotError):
    """증권사/거래소에 없는 종목코드."""


class StrategyEvaluationError(QuantPilotError):
    """전략 조건 평가 중 오류."""


class OrderOutcomeUnknownError(QuantPilotError):
    """주문이 브로커에 접수됐는지 알 수 없음 (요청 전송 후 타임아웃/연결 끊김/응답 파싱 실패,
    또는 대사(reconciliation) 조회 결과가 한 건으로 특정되지 않음).

    BrokerAPIError의 하위 클래스가 *아니다* — Celery autoretry 대상에 걸려 같은 주문이
    다시 전송되면 중복 주문이 될 수 있기 때문이다. 이 예외가 나면 주문을 UNKNOWN(미확정)으로
    두고, 브로커 주문 조회로 대사가 끝나기 전까지 절대 재전송하지 않는다.
    """
