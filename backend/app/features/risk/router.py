from fastapi import APIRouter

from app.features.risk.guard import RiskGuard
from app.features.risk.schemas import KillSwitchRequest, KillSwitchStatus

router = APIRouter(prefix="/risk", tags=["risk"])
_guard = RiskGuard()


@router.post("/kill-switch/engage", response_model=KillSwitchStatus)
async def engage_kill_switch(payload: KillSwitchRequest) -> KillSwitchStatus:
    """앱의 '비상 정지' 버튼이 호출하는 엔드포인트. 즉시 모든 신규 주문을 차단한다."""
    await _guard.engage_kill_switch(payload.reason)
    return KillSwitchStatus(engaged=True)


@router.post("/kill-switch/release", response_model=KillSwitchStatus)
async def release_kill_switch() -> KillSwitchStatus:
    await _guard.release_kill_switch()
    return KillSwitchStatus(engaged=False)


@router.get("/kill-switch", response_model=KillSwitchStatus)
async def get_kill_switch_status() -> KillSwitchStatus:
    allowed = await _guard.is_trading_allowed()
    return KillSwitchStatus(engaged=not allowed)
