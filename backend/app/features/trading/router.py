from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.session import get_db
from app.features.trading.repository import SqlAlchemyOrderRepository
from app.features.trading.schemas import OrderOut
from app.features.trading.service import TradingService

router = APIRouter(prefix="/orders", tags=["orders"], dependencies=[Depends(get_current_user)])


def get_trading_service(db: AsyncSession = Depends(get_db)) -> TradingService:
    return TradingService(SqlAlchemyOrderRepository(db))


@router.get("", response_model=list[OrderOut])
async def list_orders(service: TradingService = Depends(get_trading_service)) -> list[OrderOut]:
    orders = await service.list_orders()
    return [OrderOut.model_validate(o) for o in orders]
