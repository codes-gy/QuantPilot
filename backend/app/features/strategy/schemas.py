from pydantic import BaseModel

from app.features.strategy.models import StrategyStatus


class StrategyCreate(BaseModel):
    name: str
    asset_class: str
    symbol: str
    entry_rule: dict
    exit_rule: dict
    max_position_size: float
    stop_loss_pct: float


class StrategyOut(StrategyCreate):
    id: int
    status: StrategyStatus

    model_config = {"from_attributes": True}
