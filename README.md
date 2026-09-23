# QuantPilot

시장을 실시간 감시하고, 설정한 전략에 맞춰 자동으로 주식(추후 코인)을 매매해 주는
**개인용** 스마트 자산 관리 앱입니다. 다중 테넌트 SaaS가 아니라 1인 사용자 기준으로
설계되어 있습니다.

- 아키텍처와 데이터 흐름, 안전장치 설계: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- 백엔드(FastAPI): [`backend/`](./backend)
- 프론트엔드(Flutter): [`frontend/`](./frontend)

## 특징

- **모의/실전 완전 분리**: `TRADING_MODE`(paper/live) 하나로만 전환, 자격증명도 분리 보관
- **비상 정지(kill switch)**: 버튼 한 번으로 모든 신규 주문 즉시 차단
- **손절/포지션 한도**: 전략별 리스크 가드가 주문 제출 전 항상 재확인
- **헥사고날 아키텍처(포트 & 어댑터)**: 도메인 로직이 DB·Redis·브로커 API 등 인프라를
  직접 알지 않도록 각 기능이 `ports.py`(인터페이스) + 어댑터 + 서비스 구조로 분리됨
- **자산군 확장 가능 구조**: 브로커 어댑터가 공용 인터페이스로 설계돼 있어 KIS(국내주식)
  외 거래소(Upbit 등) 추가가 용이함

## 기술 스택

| 영역 | 구성 |
|---|---|
| 백엔드 | FastAPI, SQLAlchemy(async) + Alembic, Celery + Redis, PostgreSQL, JWT(pyjwt) + passlib |
| 프론트엔드 | Flutter, Riverpod(상태관리/DI), Dio(REST), WebSocket, fl_chart |
| 인프라 | Docker Compose (api, ingestor, strategy-runner, celery-worker, celery-beat, postgres, redis) |
| 1차 연동 브로커 | 한국투자증권 KIS Developers (국내 주식) |
| 2차 연동 예정 | Upbit (코인) |

## 빠른 시작

```bash
cp .env.example .env   # KIS/Upbit 자격증명 등 채워넣기 (아직 없다면 비워둬도 paper 이전 개발은 가능)
docker compose up --build
```

- API: http://localhost:8000 (`/health`로 상태 확인, `/docs`에서 API 문서)
- 최초 실행 시 마이그레이션과 계정 생성이 필요합니다 — [`backend/README.md`](./backend/README.md) 참고

```bash
cd frontend
flutter pub get
flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1 --dart-define=WS_URL=ws://localhost:8000/ws/live
```

## 진행 현황

| 단계 | 내용 | 상태 |
|---|---|---|
| 인증 | JWT 기반 라우터 보호, CLI 계정 생성(`scripts/create_user.py`) | ✅ |
| 아키텍처 | 헥사고날(포트 & 어댑터) 전체 적용 | ✅ |
| 주문 실행 파이프라인 | `OrderExecutionFacade` — 리스크 재확인/멱등성/브로커 호출/포지션 갱신 | ✅ |
| 전략 러너 | 활성 전략 동적 로드, 손절/포지션 한도 실연결 | ✅ |
| 시세 수집기 | 감시 종목 동적 로드 (활성 전략 기반) | ✅ |
| KIS/Upbit 실연동 | 인증, 주문, 실시간 시세 WebSocket | ⬜ (앱키 발급 후) |
| 일일 손실 한도 | 전체 계좌 단위 서킷브레이커 | ⬜ |

세부 설계는 [`ARCHITECTURE.md`](./ARCHITECTURE.md), 다음 단계 후보는 그 문서 8절을 참고하세요.

