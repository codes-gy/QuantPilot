from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.features.account.repository import SqlAlchemyUserRepository
from app.features.account.schemas import LoginRequest, TokenResponse
from app.features.account.service import AccountService

router = APIRouter(prefix="/auth", tags=["auth"])


def get_account_service(db: AsyncSession = Depends(get_db)) -> AccountService:
    """조립 지점: 여기서만 구체 어댑터(SqlAlchemyUserRepository)를 선택한다."""
    return AccountService(SqlAlchemyUserRepository(db))


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, service: AccountService = Depends(get_account_service)
) -> TokenResponse:
    token = await service.authenticate(payload.email, payload.password)
    if token is None:
        raise HTTPException(status_code=401, detail="invalid credentials")
    return TokenResponse(access_token=token)
