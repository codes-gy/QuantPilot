from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.features.strategy.models import StrategyStatus
from app.features.strategy.repository import SqlAlchemyStrategyRepository
from app.features.strategy.schemas import StrategyCreate, StrategyOut
from app.features.strategy.service import (
    InvalidStrategyError,
    StrategyActiveError,
    StrategyNotFoundError,
    StrategyService,
)

router = APIRouter(prefix="/strategies", tags=["strategies"], dependencies=[Depends(get_current_user)])


def get_strategy_service(db: AsyncSession = Depends(get_db)) -> StrategyService:
    return StrategyService(SqlAlchemyStrategyRepository(db))


@router.post("", response_model=StrategyOut)
async def create_strategy(
    payload: StrategyCreate, service: StrategyService = Depends(get_strategy_service)
) -> StrategyOut:
    strategy = await service.create_strategy(payload)
    return StrategyOut.model_validate(strategy)


@router.get("", response_model=list[StrategyOut])
async def list_strategies(service: StrategyService = Depends(get_strategy_service)) -> list[StrategyOut]:
    strategies = await service.list_strategies()
    return [StrategyOut.model_validate(s) for s in strategies]


async def _set_status(service: StrategyService, strategy_id: int, status: StrategyStatus) -> StrategyOut:
    try:
        strategy = await service.set_status(strategy_id, status)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStrategyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StrategyOut.model_validate(strategy)


@router.post("/{strategy_id}/activate", response_model=StrategyOut)
async def activate_strategy(
    strategy_id: int, service: StrategyService = Depends(get_strategy_service)
) -> StrategyOut:
    """전략을 켠다. strategy-runner/ingestor가 다음 갱신 주기(최대 30초) 안에 감시를 시작한다."""
    return await _set_status(service, strategy_id, StrategyStatus.ACTIVE)


@router.post("/{strategy_id}/pause", response_model=StrategyOut)
async def pause_strategy(
    strategy_id: int, service: StrategyService = Depends(get_strategy_service)
) -> StrategyOut:
    """전략을 끈다. 신규 주문뿐 아니라 보유 포지션의 손절/익절 감시도 멈춘다."""
    return await _set_status(service, strategy_id, StrategyStatus.PAUSED)


@router.put("/{strategy_id}", response_model=StrategyOut)
async def update_strategy(
    strategy_id: int, payload: StrategyCreate, service: StrategyService = Depends(get_strategy_service)
) -> StrategyOut:
    """꺼진 전략의 설정을 바꾼다 (상태는 그대로 꺼진 상태 유지). 실행 중이면 409."""
    try:
        strategy = await service.update_strategy(strategy_id, payload)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StrategyActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return StrategyOut.model_validate(strategy)


@router.delete("/{strategy_id}", status_code=204)
async def delete_strategy(
    strategy_id: int, service: StrategyService = Depends(get_strategy_service)
) -> None:
    """꺼진 전략을 삭제한다. 실행 중이면 409. 과거 주문 기록(orders.strategy_id)은 남는다."""
    try:
        await service.delete_strategy(strategy_id)
    except StrategyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except StrategyActiveError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
