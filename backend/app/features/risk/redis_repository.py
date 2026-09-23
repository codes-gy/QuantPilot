from datetime import UTC, datetime, timedelta

from app.db.redis import get_redis
from app.features.risk.ports import DailyPnlRepository, KillSwitchRepository

_KILL_SWITCH_KEY = "kill_switch:global"
_KST_OFFSET = timedelta(hours=9)
_DAILY_PNL_TTL_SECONDS = 2 * 24 * 60 * 60  # 2일 — 자정 직후에도 전날 값이 잠시 남아있어도 무해


class RedisKillSwitchRepository(KillSwitchRepository):
    async def is_engaged(self) -> bool:
        redis = get_redis()
        value = await redis.get(_KILL_SWITCH_KEY)
        return value == "true"

    async def engage(self) -> None:
        redis = get_redis()
        await redis.set(_KILL_SWITCH_KEY, "true")

    async def release(self) -> None:
        redis = get_redis()
        await redis.delete(_KILL_SWITCH_KEY)


def _today_key() -> str:
    # KIS/국내 거래 기준이므로 KST(UTC+9) 날짜로 하루를 구분한다.
    kst_today = (datetime.now(UTC) + _KST_OFFSET).date()
    return f"daily_pnl:{kst_today.isoformat()}"


class RedisDailyPnlRepository(DailyPnlRepository):
    async def record_realized_pnl(self, amount: float) -> float:
        redis = get_redis()
        key = _today_key()
        total = await redis.incrbyfloat(key, amount)
        await redis.expire(key, _DAILY_PNL_TTL_SECONDS)
        return float(total)

    async def get_today_realized_pnl(self) -> float:
        redis = get_redis()
        raw = await redis.get(_today_key())
        return float(raw) if raw is not None else 0.0
