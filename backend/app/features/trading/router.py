from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.features.trading import service
from app.features.trading.schemas import OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("", response_model=list[OrderOut])
async def list_orders(db: AsyncSession = Depends(get_db)) -> list[OrderOut]:
    orders = await service.list_orders(db)
    return [OrderOut.model_validate(o) for o in orders]
