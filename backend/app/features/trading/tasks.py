"""주문 실행 Celery task. 부수효과(실제 브로커 API 호출)가 있는 유일한 지점이므로
재시도/멱등성 처리가 이 모듈에 집중된다.

흐름: strategy.runner가 신호 감지 -> delay() 호출 -> 워커가 OrderExecutionFacade에 위임
     (리스크 재확인 -> 주문 기록 -> BrokerAdapter.place_order -> 결과 반영, 전부 파사드 안에서 처리)

Celery task 자체는 동기 컨텍스트이므로, 매 실행마다 독립된 DB 세션을 열고
asyncio.run으로 파사드(비동기)를 호출한다 — FastAPI 요청 스코프 세션과는 무관하다.
"""

import asyncio

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.exceptions import BrokerAPIError, KillSwitchEngagedError, RiskLimitExceededError
from app.db.session import AsyncSessionLocal
from app.features.broker.base import AssetClass
from app.features.broker.factory import get_broker_adapter
from app.features.notification.factory import get_notification_service
from app.features.risk.guard import RiskGuard
from app.features.risk.redis_repository import RedisDailyPnlRepository, RedisKillSwitchRepository
from app.features.trading.facade import OrderExecutionFacade
from app.features.trading.repository import SqlAlchemyOrderRepository, SqlAlchemyPositionRepository


async def _submit_order(
    *,
    client_order_id: str,
    symbol: str,
    side: str,
    asset_class: str,
    quantity: float,
    order_type: str,
    price: float | None,
    strategy_id: int | None,
) -> str:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        facade = OrderExecutionFacade(
            orders=SqlAlchemyOrderRepository(db),
            positions=SqlAlchemyPositionRepository(db),
            risk_guard=RiskGuard(
                kill_switch=RedisKillSwitchRepository(),
                notifier=get_notification_service(),
                daily_pnl=RedisDailyPnlRepository(),
                daily_loss_limit_krw=settings.daily_loss_limit_krw,
            ),
            broker=get_broker_adapter(AssetClass(asset_class)),
        )
        order = await facade.submit_order(
            symbol=symbol,
            side=side,
            asset_class=asset_class,
            quantity=quantity,
            order_type=order_type,
            price=price,
            client_order_id=client_order_id,
            strategy_id=strategy_id,
            trading_mode=settings.trading_mode.value,
        )
        return order.client_order_id


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=2,
    autoretry_for=(BrokerAPIError,),
)
def submit_order_task(
    self,
    *,
    client_order_id: str,
    symbol: str,
    side: str,
    quantity: float,
    asset_class: str = AssetClass.KR_STOCK.value,
    order_type: str = "market",
    price: float | None = None,
    strategy_id: int | None = None,
) -> str:
    """client_order_id는 호출부(strategy.runner)가 신호 발생 시점에 미리 발급해 넘겨야
    한다 — 그래야 이 task가 재시도돼도 매번 동일한 키로 브로커에 전송되어 중복 주문을
    막을 수 있다.

    KillSwitchEngagedError/RiskLimitExceededError는 재시도 대상이 아니다 — 비상 정지나
    리스크 한도 초과는 시간이 지난다고 해결되는 문제가 아니므로 즉시 실패시키고
    감사 로그(RiskGuard가 이미 알림을 보낸다)에 맡긴다.
    """
    try:
        return asyncio.run(
            _submit_order(
                client_order_id=client_order_id,
                symbol=symbol,
                side=side,
                asset_class=asset_class,
                quantity=quantity,
                order_type=order_type,
                price=price,
                strategy_id=strategy_id,
            )
        )
    except (KillSwitchEngagedError, RiskLimitExceededError):
        raise
