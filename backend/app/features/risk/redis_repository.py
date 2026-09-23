from app.db.redis import get_redis
from app.features.risk.ports import KillSwitchRepository

_KILL_SWITCH_KEY = "kill_switch:global"


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
