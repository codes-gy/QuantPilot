from fastapi import APIRouter, Depends

from app.core.config import get_settings
from app.core.deps import get_current_user
from app.features.notification.factory import get_notification_service
from app.features.risk.guard import RiskGuard
from app.features.risk.redis_repository import RedisDailyPnlRepository, RedisKillSwitchRepository
from app.features.risk.schemas import DailyPnlStatus, KillSwitchRequest, KillSwitchStatus

router = APIRouter(prefix="/risk", tags=["risk"], dependencies=[Depends(get_current_user)])


def get_risk_guard() -> RiskGuard:
    """조립 지점: 여기서만 구체 어댑터(Redis, WS 알림)를 선택한다."""
    settings = get_settings()
    return RiskGuard(
        kill_switch=RedisKillSwitchRepository(),
        notifier=get_notification_service(),
        daily_pnl=RedisDailyPnlRepository(),
        daily_loss_limit_krw=settings.daily_loss_limit_krw,
    )


@router.post("/kill-switch/engage", response_model=KillSwitchStatus)
async def engage_kill_switch(
    payload: KillSwitchRequest, guard: RiskGuard = Depends(get_risk_guard)
) -> KillSwitchStatus:
    """앱의 '비상 정지' 버튼이 호출하는 엔드포인트. 즉시 모든 신규 주문을 차단한다."""
    await guard.engage_kill_switch(payload.reason)
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
