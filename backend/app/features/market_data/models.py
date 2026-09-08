"""시계열 시세 영속화 모델 (백테스트/분석용 — 실시간 조회는 Redis 캐시를 사용).

대용량 tick/candle 저장 시 PostgreSQL에 TimescaleDB 확장을 얹어 하이퍼테이블로
전환하는 것을 권장 (초기에는 일반 테이블 + 시간 인덱스로 시작).
"""

from datetime import datetime

from sqlalchemy import Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Candle(Base):
    __tablename__ = "candles"
    __table_args__ = (Index("ix_candles_symbol_ts", "asset_class", "symbol", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_class: Mapped[str] = mapped_column(index=True)
    symbol: Mapped[str] = mapped_column(index=True)
    interval: Mapped[str]  # "1m", "5m", "1d" ...
    timestamp: Mapped[datetime]
    open: Mapped[float]
    high: Mapped[float]
    low: Mapped[float]
    close: Mapped[float]
    volume: Mapped[float]
