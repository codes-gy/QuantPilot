from pydantic import BaseModel

from app.features.trading.models import OrderStatus


class OrderOut(BaseModel):
    id: int
    client_order_id: str
    broker_order_id: str | None
    symbol: str
    side: str
    quantity: float
    status: OrderStatus
    filled_quantity: float
    trading_mode: str

    model_config = {"from_attributes": True}
