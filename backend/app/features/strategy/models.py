from datetime import datetime
from enum import StrEnum

from sqlalchemy import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class StrategyStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    asset_class: Mapped[str]
    symbol: Mapped[str] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(default=StrategyStatus.PAUSED)

    # 규칙 기반 조건을 JSON으로 저장 (예: {"type": "ma_cross", "fast": 5, "slow": 20})
    # engine.py의 evaluate()가 type을 보고 해당 룰 핸들러로 디스패치한다.
    entry_rule: Mapped[dict] = mapped_column(JSON)
    exit_rule: Mapped[dict] = mapped_column(JSON)

    max_position_size: Mapped[float]
    stop_loss_pct: Mapped[float]  # risk.guard가 체크하는 손절 기준

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
