"""계정 서비스가 의존하는 포트(추상 인터페이스).

AccountService는 이 인터페이스에만 의존하고, 실제 저장소 구현(SQLAlchemy 등)은
router.py의 조립 지점에서만 선택한다 — 저장소를 바꾸거나 테스트용 in-memory
구현체로 교체해도 service.py는 수정할 필요가 없어야 한다.
"""

from abc import ABC, abstractmethod

from app.features.account.models import User


class UserRepository(ABC):
    @abstractmethod
    async def get_by_email(self, email: str) -> User | None: ...

    @abstractmethod
    async def get_by_id(self, user_id: int) -> User | None: ...

    @abstractmethod
    async def add(self, user: User) -> User: ...
