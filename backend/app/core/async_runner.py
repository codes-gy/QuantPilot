"""동기 컨텍스트(Celery task)에서 코루틴을 실행하기 위한 헬퍼.

Celery task는 실행마다 asyncio.run으로 새 이벤트 루프를 만든다. 그런데 SQLAlchemy async
엔진의 커넥션 풀과 lru_cache된 Redis 클라이언트는 모듈 전역이라, 이전 루프에서 만든
연결을 다음 루프에서 재사용하다가 "attached to a different loop" / "Event loop is closed"
오류로 task가 번갈아 실패한다. 실행이 끝날 때마다 두 연결을 같은 루프 안에서 정리해서
다음 실행은 항상 새 연결로 시작하게 한다.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from app.db.redis import get_redis
from app.db.session import engine

T = TypeVar("T")


async def _dispose_loop_bound_clients() -> None:
    await engine.dispose()
    if get_redis.cache_info().currsize:
        await get_redis().aclose()
        get_redis.cache_clear()


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    async def _wrapped() -> T:
        try:
            return await coro
        finally:
            await _dispose_loop_bound_clients()

    return asyncio.run(_wrapped())
