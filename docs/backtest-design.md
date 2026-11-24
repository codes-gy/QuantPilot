# 백테스트 엔진 설계 (초안)

상태: 설계만 있음, 구현 전. 추적 이슈는 GitHub Issues의 "백테스트 엔진" 항목을 참고.

## 목표

- 활성화하기 전의 전략(`entry_rule`, `exit_rule`, `stop_loss_pct`, `max_position_size`)을 과거
  시세로 돌려서 손익, 최대 낙폭, 거래 횟수를 확인한다.
- **실거래와 같은 판단 코드를 쓴다.** 백테스트 전용 규칙 해석기를 따로 만들면 실거래와 결과가
  어긋난다. `strategy/engine.py`(`evaluate_entry`, `evaluate_exit`)와 `RiskGuard`의 손절/포지션
  한도 판단을 그대로 재사용한다.

## 범위 밖 (1차)

- 호가창/체결 강도 기반의 정밀한 체결 시뮬레이션, 슬리피지 모델링(고정 bp 정도만)
- 여러 전략을 한 계좌에서 함께 돌리는 포트폴리오 백테스트
- 파라미터 최적화(그리드 서치 등)

## 구조

```
features/backtest/
├── ports.py         # HistoricalPriceSource (과거 시세 포트)
├── engine.py        # 순수 시뮬레이션 루프 (I/O 없음)
├── broker.py        # SimulatedBroker(BrokerAdapter) — 즉시/다음 봉 체결
├── repository.py    # 결과 저장 (backtest_runs, backtest_trades)
├── service.py       # 실행 오케스트레이션
└── router.py        # POST /backtests, GET /backtests/{id}
```

1. **시세 소스 (`HistoricalPriceSource` 포트)**: `get_candles(asset_class, symbol, start, end, interval)`.
   - 1차 어댑터: KIS 기간별 시세 조회 / Upbit 캔들 API에서 받아 PostgreSQL `candles` 테이블에
     캐시한다. `candles` 모델(`market_data/models.py`)은 있지만 지금은 ingestor가 채우지 않으므로,
     틱을 봉으로 집계해 저장하는 작업은 별도로 필요하다.
2. **시뮬레이션 루프 (`engine.py`)**: 캔들을 시간순으로 순회하면서 러너와 같은 순서로 판단한다.
   손절 → `exit_rule` → (포지션 없을 때) `entry_rule`. 러너의 `_evaluate_strategy`에서 I/O 없는
   판단 부분을 순수 함수로 분리해 러너와 백테스트가 함께 쓰도록 리팩터링하는 것이 선행 작업이다.
3. **체결 모델 (`SimulatedBroker`)**: 신호가 난 봉의 *다음 봉 시가*에 체결한다(미래 데이터 참조
   방지). 수수료/세금은 자산군별 설정값으로 반영한다. `OrderExecutionFacade`를 인메모리 저장소와
   함께 그대로 써서 포지션/실현손익 계산도 실거래 코드와 같게 유지한다.
4. **결과**: 총 수익률, 최대 낙폭(MDD), 승률, 거래 목록. `backtest_runs` / `backtest_trades`
   테이블에 저장하고 앱에서 조회한다.
5. **실행 위치**: 기간이 길면 수 초 이상 걸릴 수 있어 Celery task로 실행하고, 상태를 폴링하거나
   기존 `/ws/live` 채널로 완료 알림을 보낸다. 1GB 운영 서버의 메모리를 고려해 동시 실행은 1개로
   제한한다.

## 검증 계획

- 고정된 캔들 시퀀스에 대해 기대 거래 목록과 손익이 정확히 나오는지 확인하는 단위 테스트
  (예: 임계값 매수 → 손절, 이동평균 교차 진입/청산).
- 같은 시세를 러너 경로와 백테스트 경로에 흘렸을 때 신호가 같은지 확인하는 회귀 테스트.

## 단계

1. 러너 판단 로직을 순수 함수로 분리 (동작 변경 없음, 기존 테스트로 보호)
2. `HistoricalPriceSource` + DB 캔들 어댑터
3. `engine.py` + `SimulatedBroker` + 단위 테스트
4. 결과 저장/조회 API, Celery 실행
5. 프론트엔드 결과 화면
