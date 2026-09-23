"""계정 애플리케이션 서비스 — UserRepository 포트에만 의존한다 (SQLAlchemy를 모른다)."""

from app.core.security import create_access_token, hash_password, verify_password
from app.features.account.models import User
from app.features.account.ports import UserRepository


class AccountService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def authenticate(self, email: str, password: str) -> str | None:
        user = await self._users.get_by_email(email)
        if user is None or not verify_password(password, user.hashed_password):
            return None
        return create_access_token(subject=str(user.id))

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._users.get_by_id(user_id)

    async def create_user(self, email: str, plain_password: str) -> User:
        user = User(email=email, hashed_password=hash_password(plain_password))
        return await self._users.add(user)
