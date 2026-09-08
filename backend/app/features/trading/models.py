from datetime import datetime
from enum import StrEnum

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrderStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 재시도 시 중복 주문 방지용 멱등성 키 (unique). Celery task 재시도 시 이 값으로 먼저 조회한다.
    client_order_id: Mapped[str] = mapped_column(unique=True, index=True)
    broker_order_id: Mapped[str | None]

    strategy_id: Mapped[int | None] = mapped_column(index=True)
    asset_class: Mapped[str]
    symbol: Mapped[str] = mapped_column(index=True)
    side: Mapped[str]  # buy | sell
    order_type: Mapped[str]  # market | limit
    quantity: Mapped[float]
    price: Mapped[float | None]

    status: Mapped[str] = mapped_column(default=OrderStatus.PENDING)
    filled_quantity: Mapped[float] = mapped_column(default=0.0)
    avg_fill_price: Mapped[float | None]

    trading_mode: Mapped[str]  # paper | live — 어떤 모드에서 나간 주문인지 반드시 기록
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_class: Mapped[str]
    symbol: Mapped[str] = mapped_column(unique=True, index=True)
    quantity: Mapped[float]
    avg_entry_price: Mapped[float]
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
