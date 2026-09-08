from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스. 각 feature/models.py 가 이를 상속한다."""
