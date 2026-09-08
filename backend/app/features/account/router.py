from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.features.account import service
from app.features.account.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    token = await service.authenticate(db, payload.email, payload.password)
    if token is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenResponse(access_token=token)
