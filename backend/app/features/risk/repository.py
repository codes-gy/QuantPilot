"""KillSwitchAuditLogRepository 포트의 SQLAlchemy 구현체.

kill switch on/off 상태 자체(RedisKillSwitchRepository)와 달리, 이건 Postgres에
영구 기록한다 — Redis는 재기동/장애 시 사라질 수 있는 상태 저장용이고, 감사 추적은
지워지면 안 되기 때문이다.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.risk.models import KillSwitchAuditLog
from app.features.risk.ports import KillSwitchAuditLogRepository


class SqlAlchemyKillSwitchAuditLogRepository(KillSwitchAuditLogRepository):
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def record(self, reason: str) -> None:
        self._db.add(KillSwitchAuditLog(reason=reason))
        await self._db.commit()

    async def list_recent(self, limit: int = 50) -> list[KillSwitchAuditLog]:
        result = await self._db.execute(
            select(KillSwitchAuditLog).order_by(KillSwitchAuditLog.engaged_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
