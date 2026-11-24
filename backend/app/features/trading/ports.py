"""trading 서비스/task가 의존하는 포트."""

from abc import ABC, abstractmethod
from datetime import datetime

from app.features.trading.models import Order, Position


class OrderRepository(ABC):
    @abstractmethod
    async def list_recent(self, limit: int = 50) -> list[Order]: ...

    @abstractmethod
    async def get_by_client_order_id(self, client_order_id: str) -> Order | None:
        """Celery task 재시도 시 중복 주문 방지용 조회."""
        ...

    @abstractmethod
    async def list_pending(self) -> list[Order]:
        """아직 최종 상태(FILLED/REJECTED/CANCELLED)에 도달하지 않은 주문 목록.
        체결 확인 폴링(poll_pending_order_fills)이 매 주기 이 목록을 조회한다.
        """
        ...

    @abstractmethod
    async def list_unknown(self) -> list[Order]:
        """UNKNOWN(미확정) 상태 주문 목록. 브로커 주문 조회로 대사해야 하는 대상이다."""
        ...

    @abstractmethod
    async def list_broker_order_ids(self, symbol: str, since: datetime) -> set[str]:
        """since(UTC, naive) 이후 생성된 해당 종목 주문들 중 이미 브로커 주문번호가 연결된 것.
        대사할 때 다른 주문에 이미 연결된 브로커 주문을 후보에서 빼는 데 쓴다.
        """
        ...

    @abstractmethod
    async def add(self, order: Order) -> Order: ...

    @abstractmethod
    async def update(self, order: Order) -> Order: ...


class PositionRepository(ABC):
    @abstractmethod
    async def get_by_symbol(self, symbol: str) -> Position | None: ...

    @abstractmethod
    async def upsert(self, position: Position) -> Position: ...

    @abstractmethod
    async def list_all(self) -> list[Position]:
        """대시보드의 보유 포지션 요약(GET /positions)이 사용한다."""
        ...
