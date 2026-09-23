# QuantPilot Backend

FastAPI 기반 백엔드. 구조와 설계 배경은 저장소 루트의 `ARCHITECTURE.md`를 참고하세요.

## 로컬 실행 (Docker Compose)

```bash
cp .env.example .env   # KIS/Upbit 자격증명 등 채워넣기
docker compose up --build
```

- API: http://localhost:8000 (`/health`로 상태 확인)
- API 문서: http://localhost:8000/docs

## 서비스 구성

`api`, `ingestor`(시세 수집), `strategy-runner`(전략 평가), `celery-worker`(주문 실행),
`celery-beat`(정기 작업), `postgres`, `redis` — 각 역할은 `ARCHITECTURE.md` 3절 참고.

## 사용자 계정 생성

공개 회원가입 엔드포인트는 없다 (개인용 프로젝트라 외부에 노출하지 않기 위함).
마이그레이션 적용 후 CLI로 최초 계정을 생성한다:

```bash
docker compose exec api python -m scripts.create_user user@example.com
```

이후 `/auth/login`으로 로그인해 발급받은 JWT를 `Authorization: Bearer <token>` 헤더로
사용한다. `/health`, `/auth/login`을 제외한 모든 REST 엔드포인트와 `/ws/live`(쿼리
파라미터 `?token=<access_token>`)가 이 토큰을 요구한다.

## 마이그레이션

```bash
docker compose exec api alembic revision --autogenerate -m "message"
docker compose exec api alembic upgrade head
```

## 테스트

```bash
docker compose exec api pytest
```
