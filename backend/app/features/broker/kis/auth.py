"""KIS OAuth 접근토큰 발급/갱신.

KIS 접근토큰은 발급 후 24시간(실제로는 최대 86400초, 문서상 최대 90일이지만 보수적으로
매 6시간마다 celery-beat가 갱신하도록 운영) 유효. Redis(kis:token:{live|paper})에
캐싱해 REST/WS 클라이언트가 공유한다.
"""

from dataclasses import dataclass

import httpx

from app.core.exceptions import BrokerAPIError
from app.core.logging import get_logger
from app.db.redis import get_redis

logger = get_logger(__name__)

_TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 300  # 만료 5분 전에는 캐시를 비워 재발급 유도


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

    async def refresh_token(self) -> str:
        """캐시 여부와 무관하게 강제로 재발급한다 (celery-beat 정기 갱신용)."""
        return await self._issue_token()

    async def _issue_token(self) -> str:
        """POST {base_url}/oauth2/tokenP — 접근토큰 발급.

        응답의 expires_in(초)에서 안전마진을 뺀 시간을 TTL로 Redis에 캐싱한다.
        """
        creds = self._credentials
        async with httpx.AsyncClient(base_url=creds.base_url, timeout=10.0) as http:
            response = await http.post(
                "/oauth2/tokenP",
                headers={"content-type": "application/json"},
                json={
                    "grant_type": "client_credentials",
                    "appkey": creds.app_key,
                    "appsecret": creds.app_secret,
                },
            )

        if response.status_code != 200:
            raise BrokerAPIError(
                f"KIS token issuance failed ({self._mode_key}): "
                f"{response.status_code} {response.text}"
            )

        data = response.json()
        access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        ttl = max(expires_in - _TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS, 60)

        redis = get_redis()
        await redis.set(f"kis:token:{self._mode_key}", access_token, ex=ttl)
        logger.info("KIS access token issued (%s), ttl=%ss", self._mode_key, ttl)
        return access_token

    async def get_approval_key(self) -> str:
        """POST {base_url}/oauth2/Approval — 실시간 WebSocket 접속용 approval_key 발급.

        접근토큰과는 별도 발급 절차이며, 요청 필드명이 "secretkey"인 점에 유의
        (tokenP는 "appsecret"을 쓰지만 이 엔드포인트는 다르다).
        """
        creds = self._credentials
        async with httpx.AsyncClient(base_url=creds.base_url, timeout=10.0) as http:
            response = await http.post(
                "/oauth2/Approval",
                headers={"content-type": "application/json"},
                json={
                    "grant_type": "client_credentials",
                    "appkey": creds.app_key,
                    "secretkey": creds.app_secret,
                },
            )

        if response.status_code != 200:
            raise BrokerAPIError(
                f"KIS approval key issuance failed ({self._mode_key}): "
                f"{response.status_code} {response.text}"
            )

        return response.json()["approval_key"]
