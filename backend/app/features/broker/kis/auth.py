"""KIS OAuth 접근토큰 발급/갱신.

KIS 접근토큰은 발급 후 24시간 유효. celery-beat 의 refresh_kis_token 정기 작업이
만료 전 갱신하고, Redis(kis:token:{live|paper})에 캐싱해 REST/WS 클라이언트가 공유한다.
"""

from dataclasses import dataclass

from app.db.redis import get_redis


@dataclass
class KISCredentials:
    app_key: str
    app_secret: str
    base_url: str
    account_no: str


class KISAuth:
    def __init__(self, credentials: KISCredentials, mode_key: str) -> None:
        self._credentials = credentials
        self._mode_key = mode_key  # "live" | "paper" — Redis 캐시 키 네임스페이스 분리용

    async def get_access_token(self) -> str:
        redis = get_redis()
        cached = await redis.get(f"kis:token:{self._mode_key}")
        if cached:
            return cached
        return await self._issue_token()

    async def _issue_token(self) -> str:
        # TODO: POST {base_url}/oauth2/tokenP 호출, 응답 토큰을 만료시간 - 5분 TTL로 Redis에 저장
        raise NotImplementedError

    async def get_approval_key(self) -> str:
        # TODO: 실시간 WebSocket 접속용 approval_key 발급 (POST /oauth2/Approval)
        raise NotImplementedError
