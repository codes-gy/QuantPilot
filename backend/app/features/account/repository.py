"""UserRepository 포트의 SQLAlchemy 구현체 (어댑터)."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.account.models import User
from app.features.account.ports import UserRepository


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        result = await self._db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def add(self, user: User) -> User:
        self._db.add(user)
        await self._db.commit()
        await self._db.refresh(user)
        return user
