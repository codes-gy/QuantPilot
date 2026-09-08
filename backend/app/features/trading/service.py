from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.trading.models import Order


async def list_orders(db: AsyncSession, limit: int = 50) -> list[Order]:
    result = await db.execute(select(Order).order_by(Order.created_at.desc()).limit(limit))
    return list(result.scalars().all())
