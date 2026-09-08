from pydantic import BaseModel


class KillSwitchRequest(BaseModel):
    reason: str


class KillSwitchStatus(BaseModel):
    engaged: bool
