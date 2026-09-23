from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.features.strategy.repository import SqlAlchemyStrategyRepository
from app.features.strategy.schemas import StrategyCreate, StrategyOut
from app.features.strategy.service import StrategyService

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
