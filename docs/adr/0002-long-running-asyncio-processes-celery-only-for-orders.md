# 시세 수집과 전략 평가는 상시 asyncio 프로세스로, Celery는 주문 실행과 정기 작업에만 쓴다

WebSocket을 계속 붙잡는 시세 수집(`ingestor`)과 Redis pub/sub에 반응하는 전략 평가(`strategy-runner`)는 짧은 작업 단위에 맞춘 Celery와 맞지 않아 별도 상시 프로세스로 두고, 재시도와 큐잉이 필요한 주문 제출·취소와 체결 폴링 같은 정기 작업만 Celery(`celery-worker`, `celery-beat`)에 맡겼습니다. 배경과 프로세스별 이유는 `ARCHITECTURE.md` 3절에 있습니다.

## Consequences

- Celery task는 동기 컨텍스트라 매 실행마다 `asyncio.run`으로 새 루프를 만듭니다. 모듈 전역인 SQLAlchemy 엔진 풀과 Redis 클라이언트를 루프마다 정리하지 않으면 task가 번갈아 실패하므로, task 안의 코루틴은 반드시 `app.core.async_runner.run_async`로 실행합니다(`c7cbb68`).
- 전략 러너의 중복 제출 방지 상태(`SubmitGuard`)는 러너 프로세스 메모리에만 있어 재시작하면 초기화됩니다.

근거: `ARCHITECTURE.md` 3절, `docker-compose.yml`, `backend/app/features/strategy/runner.py`, `backend/app/features/trading/tasks.py`, `8d44111`.
