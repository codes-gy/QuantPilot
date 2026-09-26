from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.features.trading.repository import SqlAlchemyOrderRepository, SqlAlchemyPositionRepository
from app.features.trading.schemas import OrderOut, PositionOut
from app.features.trading.service import TradingService

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(get_current_user)])
positions_router = APIRouter(prefix="/positions", tags=["positions"], dependencies=[Depends(get_current_user)])


def get_trading_service(db: AsyncSession = Depends(get_db)) -> TradingService:
    return TradingService(SqlAlchemyOrderRepository(db), SqlAlchemyPositionRepository(db))


@router.get("", response_model=list[OrderOut])
async def list_orders(service: TradingService = Depends(get_trading_service)) -> list[OrderOut]:
    orders = await service.list_orders()
    return [OrderOut.model_validate(o) for o in orders]


@positions_router.get("", response_model=list[PositionOut])
async def list_positions(service: TradingService = Depends(get_trading_service)) -> list[PositionOut]:
    """대시보드의 보유 포지션 요약이 사용한다. 잔고 0인 포지션은 제외된다."""
    positions = await service.list_positions()
    return [PositionOut.model_validate(p) for p in positions]
