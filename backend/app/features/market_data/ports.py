"""시세 캐시가 의존하는 포트.

ingestor(수집), strategy-runner(소비), REST API(조회)가 모두 이 인터페이스에만
의존한다 — 지금은 Redis 구현체 하나뿐이지만, 저장소를 바꾸더라도 세 호출부 중
어느 것도 수정할 필요가 없어야 한다.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from app.features.broker.base import AssetClass, Tick


class PriceCachePort(ABC):
    @abstractmethod
    async def cache_tick(self, asset_class: AssetClass, tick: Tick) -> None: ...

    @abstractmethod
    async def get_latest_price(self, asset_class: AssetClass, symbol: str) -> float | None: ...

    @abstractmethod
    def subscribe(self, asset_class: AssetClass, symbols: list[str]) -> AsyncIterator[dict]:
        """symbols에 대한 실시간 틱을 {"symbol", "price", "volume", "timestamp"} dict로 yield.

        여러 심볼을 동시에 구독하므로 "symbol" 필드로 어느 종목의 틱인지 구분해야 한다.
        """
        ...
