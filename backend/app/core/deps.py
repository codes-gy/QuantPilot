"""라우터 보호용 인증 dependency.

전략/주문/리스크/시세 라우터는 개인용 프로젝트라도 외부에 노출되면
kill switch나 전략 CRUD를 누구나 호출할 수 있게 되므로, 로그인(/auth/login)을
제외한 모든 API는 이 dependency를 거치도록 강제한다.
"""

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db.session import get_db
from app.features.account.models import User
from app.features.account.repository import SqlAlchemyUserRepository
from app.features.account.service import AccountService

_bearer_scheme = HTTPBearer(auto_error=False)

_CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise _CREDENTIALS_EXCEPTION

    try:
        user_id = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _CREDENTIALS_EXCEPTION from exc

    service = AccountService(SqlAlchemyUserRepository(db))
    user = await service.get_by_id(int(user_id))
    if user is None:
        raise _CREDENTIALS_EXCEPTION
    return user
