"""kill switch 발동 이력을 DB에 영구 기록하기 위한 모델.

kill switch 자체의 on/off 상태는 Redis(RedisKillSwitchRepository)에 있지만, "언제 왜
발동됐는지"는 알림 채널로만 전파되고 있어서 알림을 놓치면 다시 확인할 방법이 없었다.
이 테이블은 그 감사 추적(audit trail) 전용이다 — kill switch 상태 자체의 source of
truth가 아니다.
"""

from datetime import datetime

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class KillSwitchAuditLog(Base):
    __tablename__ = "kill_switch_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    reason: Mapped[str]
    engaged_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)
