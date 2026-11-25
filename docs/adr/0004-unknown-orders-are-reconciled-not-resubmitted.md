# 응답이 유실된 주문은 미확정(UNKNOWN)으로 두고 다시 보내지 않으며, 브로커 조회로 대사한다

KIS 국내주식 주문 API에는 우리 주문 키(`client_order_id`)를 실어 보낼 필드가 없어서, 타임아웃처럼 응답을 못 받은 주문을 다시 보내면 브로커 쪽에서 중복을 걸러 줄 방법이 없습니다. 그래서 중복 주문보다 주문 누락을 택했습니다. 브로커 호출 직전에 주문을 `unknown`으로 먼저 기록하고(write-ahead), 접수되지 않은 것이 확실한 실패(`BrokerAPIError`)만 `pending`으로 되돌려 Celery가 재시도하게 합니다. 응답 유실(`OrderOutcomeUnknownError`, `BrokerAPIError`의 하위 클래스가 아님)이나 워커 종료로 남은 `unknown` 주문은 재전송하지 않고, `poll_pending_order_fills`가 `BrokerAdapter.find_order`로 대사합니다. 그동안 그 종목에는 새 주문이 나가지 않습니다. 상태별 규칙과 KIS 대사의 한계는 `ARCHITECTURE.md` 5절 "중복 주문 방지 (멱등성과 대사)"에 있습니다.

## Consequences

- 대사로 판단할 수 없으면(후보 여러 건, 조회 실패, `find_order` 미구현 어댑터) `unknown`이 유지되고 사람이 브로커 화면에서 확인할 때까지 그 종목은 막힙니다. 신호를 놓치는 비용을 받아들인 결정입니다.
- 새 브로커 어댑터는 전송 전 실패·명시적 거부(`BrokerAPIError`)와 전송 후 결과 불명(`OrderOutcomeUnknownError`)을 반드시 구분해 던져야 합니다.

근거: `46dd674`(PR #6), `backend/app/features/trading/facade.py`, `backend/tests/features/test_order_reconciliation.py`.
