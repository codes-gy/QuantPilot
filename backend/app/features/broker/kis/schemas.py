from pydantic import BaseModel


class KISTokenResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int


class KISOrderResponse(BaseModel):
    rt_cd: str  # "0" == 성공
    msg_cd: str
    msg1: str
    output: dict | None = None
