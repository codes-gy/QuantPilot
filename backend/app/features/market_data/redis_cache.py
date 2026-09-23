"""PriceCachePort 포트의 Redis 구현체.

키 포맷(`price:{asset_class}:{symbol}`, `channel:price:{asset_class}:{symbol}`)이
이 파일 한 곳에만 정의되어 있어야 한다 — 다른 모듈은 PriceCachePort 인터페이스로만
접근한다.
"""

import json
from collections.abc import AsyncIterator

from app.db.redis import get_redis
from app.features.broker.base import AssetClass, Tick
from app.features.market_data.ports import PriceCachePort

_TICK_TTL_SECONDS = 30


def _price_key(asset_class: AssetClass, symbol: str) -> str:
    return f"price:{asset_class.value}:{symbol}"


def _channel(asset_class: AssetClass, symbol: str) -> str:
    return f"channel:price:{asset_class.value}:{symbol}"


class RedisPriceCache(PriceCachePort):
    async def cache_tick(self, asset_class: AssetClass, tick: Tick) -> None:
        redis = get_redis()
        payload = json.dumps(
            {"price": tick.price, "volume": tick.volume, "timestamp": tick.timestamp}
        )
        key = _price_key(asset_class, tick.symbol)
        await redis.set(key, payload, ex=_TICK_TTL_SECONDS)
        await redis.publish(_channel(asset_class, tick.symbol), payload)

    async def get_latest_price(self, asset_class: AssetClass, symbol: str) -> float | None:
        redis = get_redis()
        raw = await redis.get(_price_key(asset_class, symbol))
        if raw is None:
            return None
        return json.loads(raw)["price"]

    async def subscribe(self, asset_class: AssetClass, symbols: list[str]) -> AsyncIterator[dict]:
        """strategy/runner.py가 사용하는 pub/sub 구독 — Redis pub/sub 메시지 봉투를
        여기서 걷어내고 순수 데이터 dict만 yield해, 호출부가 Redis를 몰라도 되게 한다.
        """
        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(*[_channel(asset_class, s) for s in symbols])
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            yield json.loads(message["data"])
