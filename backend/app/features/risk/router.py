from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.core.logging import get_logger
from app.db.session import get_db
from app.features.notification.factory import get_notification_service
from app.features.risk.guard import RiskGuard
from app.features.risk.redis_repository import RedisDailyPnlRepository, RedisKillSwitchRepository
from app.features.risk.repository import SqlAlchemyKillSwitchAuditLogRepository
from app.features.risk.schemas import DailyPnlStatus, KillSwitchAuditLogEntry, KillSwitchRequest, KillSwitchStatus
from app.features.trading.tasks import poll_pending_order_fills

logger = get_logger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"], dependencies=[Depends(get_current_user)])


def get_risk_guard(db: AsyncSession = Depends(get_db)) -> RiskGuard:
    """조립 지점: 여기서만 구체 어댑터(Redis, WS 알림, DB 감사 로그)를 선택한다."""
    settings = get_settings()
    return RiskGuard(
        kill_switch=RedisKillSwitchRepository(),
        notifier=get_notification_service(),
        daily_pnl=RedisDailyPnlRepository(),
        daily_loss_limit_krw=settings.daily_loss_limit_krw,
        audit_log=SqlAlchemyKillSwitchAuditLogRepository(db),
    )


@router.post("/kill-switch/engage", response_model=KillSwitchStatus)
async def engage_kill_switch(
    payload: KillSwitchRequest, guard: RiskGuard = Depends(get_risk_guard)
) -> KillSwitchStatus:
    """앱의 '비상 정지' 버튼이 호출하는 엔드포인트. 즉시 모든 신규 주문을 차단하고,
    미체결 주문 취소 작업을 바로 한 번 실행시킨다 (놓쳐도 celery-beat가 10초마다 다시 돈다).
    """
    await guard.engage_kill_switch(payload.reason)
    try:
        poll_pending_order_fills.delay()
    except Exception:
        # 큐 연결 실패가 비상 정지 자체를 실패로 만들면 안 된다 — 주기 작업이 곧 처리한다.
        logger.exception("failed to enqueue open-order cancellation after kill switch")
    return KillSwitchStatus(engaged=True)


@router.post("/kill-switch/release", response_model=KillSwitchStatus)
async def release_kill_switch(guard: RiskGuard = Depends(get_risk_guard)) -> KillSwitchStatus:
    await guard.release_kill_switch()
    return KillSwitchStatus(engaged=False)


@router.get("/kill-switch", response_model=KillSwitchStatus)
async def get_kill_switch_status(guard: RiskGuard = Depends(get_risk_guard)) -> KillSwitchStatus:
    allowed = await guard.is_trading_allowed()
    return KillSwitchStatus(engaged=not allowed)


@router.get("/daily-pnl", response_model=DailyPnlStatus)
async def get_daily_pnl(guard: RiskGuard = Depends(get_risk_guard)) -> DailyPnlStatus:
    """앱 대시보드가 오늘 실현손익과 한도를 함께 보여주기 위한 조회용 엔드포인트."""
    settings = get_settings()
    realized = await guard.get_today_realized_pnl()
    return DailyPnlStatus(realized_pnl_krw=realized, daily_loss_limit_krw=settings.daily_loss_limit_krw)


@router.get("/kill-switch/history", response_model=list[KillSwitchAuditLogEntry])
async def get_kill_switch_history(db: AsyncSession = Depends(get_db)) -> list[KillSwitchAuditLogEntry]:
    """kill switch가 언제, 왜 발동됐었는지에 대한 감사 이력. 알림을 놓쳤을 때 되짚어보는 용도."""
    repo = SqlAlchemyKillSwitchAuditLogRepository(db)
    entries = await repo.list_recent()
    return [KillSwitchAuditLogEntry(reason=e.reason, engaged_at=e.engaged_at) for e in entries]
