"""실시간 시세 Redis 캐싱 레이어.

ingestor.py(수집)와 strategy engine(소비), REST API(조회)가 모두 이 모듈을 통해서만
Redis에 접근한다 — 키 포맷이 여기 한 곳에만 정의되어 있어야 한다.
"""

import json
import time

from app.db.redis import get_redis
from app.features.broker.base import AssetClass, Tick

_TICK_TTL_SECONDS = 30


def _price_key(asset_class: AssetClass, symbol: str) -> str:
    return f"price:{asset_class.value}:{symbol}"


def _channel(asset_class: AssetClass, symbol: str) -> str:
    return f"channel:price:{asset_class.value}:{symbol}"


async def cache_tick(asset_class: AssetClass, tick: Tick) -> None:
    redis = get_redis()
    payload = json.dumps(
        {"price": tick.price, "volume": tick.volume, "timestamp": tick.timestamp}
    )
    key = _price_key(asset_class, tick.symbol)
    await redis.set(key, payload, ex=_TICK_TTL_SECONDS)
    await redis.publish(_channel(asset_class, tick.symbol), payload)


async def get_latest_price(asset_class: AssetClass, symbol: str) -> float | None:
    redis = get_redis()
    raw = await redis.get(_price_key(asset_class, symbol))
    if raw is None:
        return None
    return json.loads(raw)["price"]


async def subscribe_price_channel(asset_class: AssetClass, symbols: list[str]):
    """strategy/runner.py 가 사용하는 pub/sub 구독 헬퍼."""
    redis = get_redis()
    pubsub = redis.pubsub()
    await pubsub.subscribe(*[_channel(asset_class, s) for s in symbols])
    return pubsub


def now_ts() -> float:
    return time.time()
