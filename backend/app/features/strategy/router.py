from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.features.strategy import service
from app.features.strategy.schemas import StrategyCreate, StrategyOut

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.post("", response_model=StrategyOut)
async def create_strategy(payload: StrategyCreate, db: AsyncSession = Depends(get_db)) -> StrategyOut:
    strategy = await service.create_strategy(db, payload)
    return StrategyOut.model_validate(strategy)


@router.get("", response_model=list[StrategyOut])
async def list_strategies(db: AsyncSession = Depends(get_db)) -> list[StrategyOut]:
    strategies = await service.list_strategies(db)
    return [StrategyOut.model_validate(s) for s in strategies]
