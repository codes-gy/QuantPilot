# QuantPilot

1인용 자동매매 앱. 백엔드는 FastAPI + Celery + 상시 asyncio 프로세스(헥사고날), 프론트엔드는 Flutter. 이 코드는 실제 돈으로 주문을 냅니다.

## 먼저 읽을 것

- **용어**: 주문·포지션·전략·리스크 개념에 이름을 붙이거나 요구를 해석할 때 `GLOSSARY.md`를 따르세요. 특히 대기(`pending`)·미확정(`unknown`)·미체결은 서로 다른 것입니다.
- **결정 기록**: 주문 재전송·대사, 운용 모드 분기, 비상 정지 저장소, 프로세스 구성을 바꾸기 전에 `docs/adr/`를 읽으세요. 되돌리는 변경이면 새 ADR을 남깁니다.
- **구조와 안전장치 상세**: 데이터 흐름이나 안전장치 동작을 확인할 때는 `ARCHITECTURE.md`(특히 5절). 코드 동작이 바뀌면 이 문서와 README를 함께 고칩니다.

## 깨면 안 되는 불변식

- **미확정(`unknown`) 주문은 자동으로 다시 보내지 않습니다.** 재전송이 허용되는 것은 브로커에 접수되지 않은 것이 확실한 `pending`뿐입니다. 브로커 호출 직전에 `unknown`으로 선기록하는 순서를 유지하고, 새 어댑터는 전송 전 실패·거부를 `BrokerAPIError`로, 전송 후 결과 불명을 `OrderOutcomeUnknownError`로 구분해 던지세요. `OrderOutcomeUnknownError`를 `BrokerAPIError`의 하위로 만들거나 `autoretry_for`에 넣으면 중복 주문이 납니다. 미확정 주문이 있는 종목에는 새 주문도 내지 않습니다(`has_open_order`).
- **모든 주문은 브로커 호출 직전에 `RiskGuard.assert_can_trade()`를 통과합니다**(`OrderExecutionFacade.submit_order`). 신호 평가 시점의 확인만으로는 부족합니다. 주문은 파사드를 거쳐서만 냅니다.
- **`TRADING_MODE` 분기와 `KIS_LIVE_*`/`KIS_PAPER_*` 선택은 `broker/factory.py`에서만** 합니다. 기본값은 `paper`이고, 주문에는 `trading_mode`를 기록합니다.
- **새 프로세스 진입점은 `get_settings().assert_safe_to_start()`를 호출합니다**(API, 전략 러너, Celery 워커가 이미 호출). 주문 신호를 내는 상시 프로세스라면 `RiskGuard.apply_startup_default(settings.kill_switch_default)`도 호출합니다.
- **비상 정지 상태의 원본은 Redis 키 `kill_switch:global`입니다.** Postgres 감사 로그로 상태를 판단하지 않습니다.
- **체결 반영은 누적 체결 수량의 차이분만** 포지션·실현손익에 더합니다(`apply_broker_fill_update`). 폴링 주기마다 같은 체결을 다시 더하면 일일 손실 한도가 틀어집니다.
- **주문 키(`client_order_id`)는 신호를 낸 쪽(전략 러너)이 발급해 task에 넘깁니다.** 재시도된 task가 같은 주문 기록을 찾는 유일한 수단입니다.

## 함정

- **Celery task 안의 코루틴은 `app.core.async_runner.run_async`로 실행하세요.** 그냥 `asyncio.run`을 쓰면 전역 DB 풀·Redis 클라이언트가 이전 루프에 묶여 task가 번갈아 실패합니다.
- **`bcrypt==4.0.1` 고정은 의도된 것입니다.** passlib 1.7.4가 bcrypt 4.1+와 호환되지 않아 올리면 계정 생성이 깨집니다.
- **`ruff`는 `requirements.txt`에 없습니다.** CI는 `ruff==0.6.9`를 따로 설치하니 로컬에서도 같은 버전을 쓰세요. CI는 `python -c "import app.main"` 임포트 스모크 테스트도 돌립니다(설정 누락·순환 임포트 검출).
- **테스트는 DB/Redis 없이 돕니다.** `tests/conftest.py`가 더미 URL을 채우고, 리스크·주문 로직은 `tests/features/conftest.py`의 인메모리 포트 구현으로 검증합니다. 새 로직도 포트에 의존하게 짜서 같은 방식으로 테스트하세요. 실제 Postgres/Redis 동작은 `docker compose`로만 확인됩니다.
- **KIS 대사(`find_order`)와 KIS 실연동은 모의투자 앱키로 검증되지 않았습니다.** 응답 필드명은 문서 기준입니다. 이 경로를 바꿀 때는 그 사실을 PR에 적으세요.
- **시각**: 모델 시각은 naive UTC(`datetime.utcnow`)이고, 일일 손익은 KST 날짜로 나뉩니다. 둘을 섞어 비교하지 마세요.
- **DB 스키마를 바꾸면 Alembic 리비전을 함께 만드세요.** 운영 compose는 기동 시 `alembic upgrade head`를 실행합니다.
- **Flutter는 3.47.9로 고정**되어 있습니다(새 stable에서 `material.dart` 폐기 경고로 analyze 실패). 버전을 올릴 때는 로컬에서 `flutter analyze`·`flutter test`를 확인한 뒤 `frontend-ci.yaml`을 같이 바꿉니다.

## 컨벤션

- 백엔드 기능은 `features/<기능>/`에 `ports.py`(ABC) → 어댑터(`repository.py`, `redis_repository.py` 등) → `service.py`로 나누고, 구체 어댑터는 `router.py`/`factory.py`에서만 조립합니다(`ARCHITECTURE.md` 6절). 서비스와 파사드는 구체 어댑터를 임포트하지 않습니다.
- 프론트엔드 기능은 `lib/features/<기능>/{data,domain,presentation}`, 상태와 DI는 Riverpod. 화면별 상태는 `frontend/PLANNING.md`.
- 커밋은 `type(scope): 한국어 요약`(`feat`/`fix`/`docs`/`ci`/`chore`, scope 예: `trading`, `risk`, `strategy`, `infra`), 본문에 문제와 변경을 적습니다. 주석과 문서는 한국어입니다.
