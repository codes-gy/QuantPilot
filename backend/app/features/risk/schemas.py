from pydantic import BaseModel


class KillSwitchRequest(BaseModel):
    reason: str


class KillSwitchStatus(BaseModel):
    engaged: bool


class DailyPnlStatus(BaseModel):
    realized_pnl_krw: float
    daily_loss_limit_krw: float | None
