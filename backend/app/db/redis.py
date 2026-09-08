from functools import lru_cache

from redis.asyncio import Redis

from app.core.config import get_settings


@lru_cache
def get_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


# Redis 키 네임스페이스 컨벤션
#   price:{asset_class}:{symbol}        -> 최신 체결가 캐시 (hash)
#   channel:price:{asset_class}:{symbol}-> pub/sub 실시간 시세 채널 (strategy-runner가 구독)
#   kill_switch:global                  -> 비상 정지 스위치 (risk.guard 가 매 주문 전 체크)
#   position:{account_id}:{symbol}      -> 실시간 보유 포지션 스냅샷
