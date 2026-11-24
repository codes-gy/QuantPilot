"""주문 실행 Celery task. 부수효과(실제 브로커 API 호출)가 있는 유일한 지점이므로
재시도/멱등성 처리가 이 모듈에 집중된다.

흐름: strategy.runner가 신호 감지 -> delay() 호출 -> 워커가 OrderExecutionFacade에 위임
     (리스크 재확인 -> 주문 기록 -> BrokerAdapter.place_order -> 결과 반영, 전부 파사드 안에서 처리)

Celery task 자체는 동기 컨텍스트이므로, 매 실행마다 독립된 DB 세션을 열고
run_async(asyncio.run + 루프별 연결 정리)로 파사드(비동기)를 호출한다 — FastAPI 요청 스코프 세션과는 무관하다.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.core.async_runner import run_async
from app.core.config import get_settings
from app.core.exceptions import BrokerAPIError, KillSwitchEngagedError, RiskLimitExceededError
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.features.broker.base import AssetClass
from app.features.broker.factory import get_broker_adapter
from app.features.notification.factory import get_notification_service
from app.features.risk.guard import RiskGuard
from app.features.risk.redis_repository import RedisDailyPnlRepository, RedisKillSwitchRepository
from app.features.risk.repository import SqlAlchemyKillSwitchAuditLogRepository
from app.features.trading.facade import OrderExecutionFacade
from app.features.trading.ports import OrderRepository
from app.features.trading.repository import SqlAlchemyOrderRepository, SqlAlchemyPositionRepository

logger = get_logger(__name__)


def _risk_guard(db: AsyncSession) -> RiskGuard:
    settings = get_settings()
    return RiskGuard(
        kill_switch=RedisKillSwitchRepository(),
        notifier=get_notification_service(),
        daily_pnl=RedisDailyPnlRepository(),
        daily_loss_limit_krw=settings.daily_loss_limit_krw,
        audit_log=SqlAlchemyKillSwitchAuditLogRepository(db),
    )


def _facade(db: AsyncSession, orders: OrderRepository, asset_class: str) -> OrderExecutionFacade:
    return OrderExecutionFacade(
        orders=orders,
        positions=SqlAlchemyPositionRepository(db),
        risk_guard=_risk_guard(db),
        broker=get_broker_adapter(AssetClass(asset_class)),
        notifier=get_notification_service(),
    )


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
        facade = _facade(db, SqlAlchemyOrderRepository(db), asset_class)
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
    한다 — 그래야 이 task가 재시도돼도 같은 주문 레코드를 다시 찾는다.

    재시도(autoretry_for=BrokerAPIError)는 "브로커에 접수되지 않은 것이 확실한" 실패에만
    일어난다. 응답이 유실된 경우(OrderOutcomeUnknownError)는 파사드가 주문을 UNKNOWN으로
    남기고 정상 반환하므로 재시도되지 않는다 — 대사는 poll_pending_order_fills가 맡는다.

    KillSwitchEngagedError/RiskLimitExceededError는 재시도 대상이 아니다 — 비상 정지나
    리스크 한도 초과는 시간이 지난다고 해결되는 문제가 아니므로 즉시 실패시키고
    감사 로그(RiskGuard가 이미 알림을 보낸다)에 맡긴다.
    """
    try:
        return run_async(
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


async def _poll_pending_order_fills() -> int:
    """주기 작업 본체. 반환값은 이번 실행에서 확인한 주문 수(로그/모니터링용).

    1. UNKNOWN(미확정) 주문을 브로커 주문 조회로 대사한다 (재전송은 하지 않는다).
    2. 미체결(ACCEPTED/PARTIALLY_FILLED 등, 브로커 주문번호가 있는 것) 주문을 처리한다.
       - kill switch가 켜져 있으면 취소한다 (비상 정지 = 신규 주문 차단 + 미체결 주문 취소).
       - 아니면 체결 여부를 확인해 포지션/손익에 반영한다.

    place_order 응답에 이미 체결 정보가 포함되는 브로커(테스트 더블 등)는 submit_order()
    시점에 이미 최종 상태가 되어 list_pending()에 애초에 걸리지 않으므로, 체결 폴링은
    KIS처럼 접수와 체결이 분리된 브로커에서만 실제로 의미가 있다.
    """
    checked = 0
    async with AsyncSessionLocal() as db:
        orders_repo = SqlAlchemyOrderRepository(db)
        facades: dict[str, OrderExecutionFacade] = {}

        def facade_for(asset_class: str) -> OrderExecutionFacade:
            # 주문마다 자기 자산군(KIS 주식 / Upbit 코인) 브로커로 확인해야 한다.
            if asset_class not in facades:
                facades[asset_class] = _facade(db, orders_repo, asset_class)
            return facades[asset_class]

        for order in await orders_repo.list_unknown():
            checked += 1
            try:
                await facade_for(order.asset_class).reconcile_unknown_order(order)
            except Exception:
                logger.exception("failed to reconcile order %s", order.client_order_id)

        kill_switch_engaged = not await _risk_guard(db).is_trading_allowed()

        for order in await orders_repo.list_pending():
            checked += 1
            facade = facade_for(order.asset_class)
            try:
                if kill_switch_engaged:
                    await facade.cancel_open_order(order)
                    logger.warning("kill switch engaged: cancelled open order %s", order.client_order_id)
                else:
                    await facade.poll_and_apply_fill(order)
            except BrokerAPIError:
                # 취소 실패(이미 체결됨 등)든 조회 실패든, 다음 주기에 다시 확인한다.
                logger.warning(
                    "failed to %s order %s, will retry next cycle",
                    "cancel" if kill_switch_engaged else "poll fill status for",
                    order.client_order_id,
                )
                continue

    return checked


@celery_app.task
def poll_pending_order_fills() -> int:
    """celery-beat 주기 작업(10초). 접수 확인만 반환하는 브로커(KIS)의 체결 여부 확인,
    UNKNOWN 주문 대사, kill switch 발동 시 미체결 주문 취소를 담당한다 (자세한 배경은
    ARCHITECTURE.md 참고). kill switch 발동 직후에는 API가 이 task를 즉시 한 번 실행시킨다.
    """
    return run_async(_poll_pending_order_fills())
