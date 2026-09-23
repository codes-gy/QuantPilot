"""시세 캐시 어댑터 조립 지점."""

from app.features.market_data.ports import PriceCachePort
from app.features.market_data.redis_cache import RedisPriceCache


def get_price_cache() -> PriceCachePort:
    return RedisPriceCache()
