from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class User(Base):
    """단일 사용자 프로젝트 기준이지만, 앱 로그인/세션 관리를 위해 최소한의 계정 모델을 둔다."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True, index=True)
    hashed_password: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
