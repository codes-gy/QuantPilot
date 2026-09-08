from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, verify_password
from app.features.account import repository


async def authenticate(db: AsyncSession, email: str, password: str) -> str | None:
    user = await repository.get_user_by_email(db, email)
    if user is None or not verify_password(password, user.hashed_password):
        return None
    return create_access_token(subject=str(user.id))
