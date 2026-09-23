from fastapi import APIRouter, Depends

from app.core.deps import get_current_user
from app.features.notification.factory import get_notification_service
from app.features.risk.guard import RiskGuard
from app.features.risk.redis_repository import RedisKillSwitchRepository
from app.features.risk.schemas import KillSwitchRequest, KillSwitchStatus

router = APIRouter(prefix="/risk", tags=["risk"], dependencies=[Depends(get_current_user)])


def get_risk_guard() -> RiskGuard:
    """조립 지점: 여기서만 구체 어댑터(Redis, WS 알림)를 선택한다."""
    return RiskGuard(
        kill_switch=RedisKillSwitchRepository(),
        notifier=get_notification_service(),
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
