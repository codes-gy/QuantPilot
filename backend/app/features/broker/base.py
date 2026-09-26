"""자산군(주식/코인)에 상관없이 동일하게 다루기 위한 공용 어댑터 인터페이스.

KIS(주식)와 Upbit(코인)는 인증 방식, 시세 채널, 주문 파라미터가 전부 다르지만
strategy/trading/risk 레이어는 이 인터페이스에만 의존한다. 새 거래소를 추가할 때
이 계약만 구현하면 나머지 레이어는 수정할 필요가 없어야 한다.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class AssetClass(StrEnum):
    KR_STOCK = "kr_stock"
    CRYPTO = "crypto"


@dataclass(frozen=True)
class Tick:
    symbol: str
    price: float
    volume: float
    timestamp: float


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Literal["buy", "sell"]
    order_type: Literal["market", "limit"]
    quantity: float
    price: float | None = None
    client_order_id: str | None = None  # 멱등성 키 — 재시도 시 중복 주문 방지


@dataclass(frozen=True)
class OrderResult:
    broker_order_id: str
    status: Literal["accepted", "rejected", "filled", "partially_filled", "cancelled"]
    filled_quantity: float = 0.0
    avg_fill_price: float | None = None
    raw: dict | None = None


@dataclass(frozen=True)
class Balance:
    cash: float
    positions: dict[str, float]  # symbol -> quantity


class BrokerAdapter(ABC):
    """주문/계좌 REST 어댑터."""

    asset_class: AssetClass

    @abstractmethod
    async def place_order(self, order: OrderRequest) -> OrderResult: ...

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> OrderResult: ...

    @abstractmethod
    async def get_balance(self) -> Balance: ...

    @abstractmethod
    async def get_order_fill_status(self, broker_order_id: str) -> OrderResult:
        """주문 접수 이후의 체결 여부를 조회한다. place_order는 접수 확인만 반환하고
        체결 여부를 포함하지 않는 브로커(KIS 등)가 있어서, trading/tasks.py의 주기 작업
        (poll_pending_order_fills)이 이 메서드로 미체결 주문을 폴링한다.
        """
        ...


class MarketDataAdapter(ABC):
    """실시간 시세 WebSocket 어댑터."""

    asset_class: AssetClass

    @abstractmethod
    async def subscribe(self, symbols: list[str]) -> AsyncIterator[Tick]: ...
