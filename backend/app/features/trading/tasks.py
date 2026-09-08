"""주문 실행 Celery task. 부수효과(실제 브로커 API 호출)가 있는 유일한 지점이므로
재시도/멱등성 처리가 이 모듈에 집중된다.

흐름: strategy.runner가 신호 감지 -> delay() 호출 -> 워커가 RiskGuard 재확인
     -> BrokerAdapter.place_order -> 결과를 Order 레코드에 반영
"""

from app.celery_app import celery_app
from app.core.exceptions import BrokerAPIError
from app.features.broker.base import AssetClass


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=2,
    autoretry_for=(BrokerAPIError,),
)
def submit_order_task(self, *, symbol: str, side: str, asset_class: str = AssetClass.KR_STOCK.value) -> str:
    """client_order_id를 태스크 호출 시점에 미리 발급해 재시도 시에도 동일 키로
    브로커에 전송해야 한다 (여기서는 골격만 표시).
    """
    # TODO:
    #  1. client_order_id로 기존 Order 존재 여부 조회 (재시도 시 중복 방지)
    #  2. asyncio.run(RiskGuard().assert_can_trade()) 등으로 kill-switch/리스크 재확인
    #     (Celery task는 동기 컨텍스트이므로 async 어댑터 호출 시 asyncio.run 또는
    #      celery의 async 지원(예: `asgiref.sync`) 사용)
    #  3. Order(status=pending) 저장
    #  4. get_broker_adapter(AssetClass(asset_class)).place_order(...) 호출
    #  5. 결과에 따라 Order 상태 갱신, 실패 시 raise BrokerAPIError로 재시도 유도
    raise NotImplementedError
