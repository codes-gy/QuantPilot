"""테스트 전역 설정.

브로커 어댑터 테스트는 생성자에서 get_settings()를 호출하는데, Settings는 DB/Redis/Celery
URL을 필수로 요구한다. 로컬 Docker에는 .env가 주입돼 있지만 CI의 pytest 단계에는 없으므로,
실제 연결 없이 설정 객체만 만들 수 있도록 더미 값을 기본값으로 넣는다 (이미 있으면 유지).
테스트는 이 URL로 실제 연결하지 않는다.
"""

import os

for _key, _value in {
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost/test",
    "REDIS_URL": "redis://localhost:6379/0",
    "CELERY_BROKER_URL": "redis://localhost:6379/1",
    "CELERY_RESULT_BACKEND": "redis://localhost:6379/2",
}.items():
    os.environ.setdefault(_key, _value)
