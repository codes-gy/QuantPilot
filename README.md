# QuantPilot

시장을 실시간 감시하고, 설정한 전략에 맞춰 자동으로 주식(추후 코인)을 매매해 주는
**개인용** 스마트 자산 관리 앱입니다. 다중 테넌트 SaaS가 아니라 1인 사용자 기준으로
설계되어 있습니다.

- 아키텍처와 데이터 흐름, 안전장치 설계: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- 백엔드(FastAPI): [`backend/`](./backend)
- 프론트엔드(Flutter): [`frontend/`](./frontend) — 화면별 구현 상태와 계획은 [`frontend/PLANNING.md`](./frontend/PLANNING.md) 참고

## 특징

- **모의/실전 완전 분리**: `TRADING_MODE`(paper/live) 하나로만 전환, 자격증명도 분리 보관
- **기동 안전장치**: 운영 환경(`APP_ENV`가 `local`/`test`가 아님)이거나 실전 모드인데
  `SECRET_KEY`가 기본값이면 기동을 거부. 실전 모드는 KIS 자격증명이 비어 있어도 거부
  (API, 전략 러너, Celery 워커 모두)
- **비상 정지(kill switch)**: 버튼 한 번으로 모든 신규 주문을 즉시 차단하고, 이미 접수된
  미체결 주문은 체결 폴링 작업이 바로(늦어도 10초 안에) 취소. `KILL_SWITCH_DEFAULT=true`면
  기동할 때마다 정지 상태로 시작
- **중복 주문 방지**: 브로커로 보내기 직전에 주문을 `unknown`(미확정)으로 기록한다. 응답이
  유실되면(타임아웃 등) 다시 보내지 않고, 브로커 주문 조회로 접수 여부를 확인(대사)한 뒤에만
  다음 주문을 낸다. 자세한 규칙과 한계는 [`ARCHITECTURE.md`](./ARCHITECTURE.md) 5절 참고
- **손절/포지션 한도**: 전략별 리스크 가드가 주문 제출 전 항상 재확인 (포지션 한도는 실제
  보유 수량 + 주문 수량 기준)
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

### 백엔드 테스트 실행

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -v
```

DB/Redis 없이도 통과합니다 (RiskGuard/OrderExecutionFacade는 포트 인터페이스에만 의존하도록
설계되어 있어, 테스트에서는 인메모리 fake로 대체합니다).

## 진행 현황

| 단계 | 내용 | 상태 |
|---|---|---|
| 인증 | JWT 기반 라우터 보호, CLI 계정 생성(`scripts/create_user.py`) | ✅ |
| 아키텍처 | 헥사고날(포트 & 어댑터) 전체 적용 | ✅ |
| 주문 실행 파이프라인 | `OrderExecutionFacade` — 리스크 재확인/재시도 시 같은 주문 레코드 재사용/브로커 호출/포지션 갱신 | ✅ |
| 응답 유실 대응 | 접수 여부를 모르는 주문은 `unknown`으로 두고 재전송 금지, 브로커 주문 조회로 대사 (KIS: 당일 주문체결조회, Upbit: identifier) | ✅ (KIS 대사는 모의투자로 실제 검증 필요) |
| 전략 러너 | 활성 전략 동적 로드, 손절/포지션 한도 실연결 | ✅ |
| 시세 수집기 | 감시 종목 동적 로드 (활성 전략 기반) | ✅ |
| KIS 실연동 | 인증, 주문, 실시간 시세 WebSocket, 체결 확인 폴링 | ✅ (모의투자 앱키로 실제 검증 필요) |
| Upbit 실연동 | 인증, 주문, 실시간 시세 WebSocket | ⬜ |
| 일일 손실 한도 | 전체 계좌 단위 서킷브레이커 (매도 체결마다 실현손익 누적, 한도 초과 시 kill switch 자동 발동) | ✅ |
| Kill switch 감사 로그 | 발동 사유를 Postgres에 영구 기록 (`GET /api/v1/risk/kill-switch/history`) | ✅ |
| 테스트 | RiskGuard/OrderExecutionFacade/주문 대사/브로커 어댑터/기동 안전장치 단위 테스트 (pytest 145개) | ✅ |
| CI | GitHub Actions — 백엔드: ruff lint + import 스모크 테스트 + pytest, 프론트엔드: flutter analyze + test (각 폴더 변경 시) | ✅ |
| 기동 안전장치 | 운영 환경 또는 live 모드에서 기본 `SECRET_KEY` 거부, live 모드에서 빈 KIS 자격증명 거부 | ✅ |
| 백테스트 | 설계만 있음 ([`docs/backtest-design.md`](./docs/backtest-design.md)) | ⬜ |

세부 설계는 [`ARCHITECTURE.md`](./ARCHITECTURE.md), 다음 단계 후보는 그 문서 8절을 참고하세요.

