# 모의/실전은 TRADING_MODE 하나로만 전환하고, 분기는 broker/factory.py 한 곳에서만 한다

실수로 실전 주문이 나가는 사고를 막으려고, 운용 모드(`paper`/`live`)를 바꾸는 스위치를 환경 변수 `TRADING_MODE` 하나로 두고 기본값을 `paper`로 고정했습니다. 모드에 따라 어댑터와 자격증명(`KIS_PAPER_*` / `KIS_LIVE_*`, 완전히 분리된 변수)을 고르는 곳은 `backend/app/features/broker/factory.py`뿐입니다. 모든 주문에는 어느 모드에서 나갔는지(`Order.trading_mode`)를 남깁니다. 실전 모드나 운영 환경에서는 기본 `SECRET_KEY`나 빈 KIS 실전 자격증명으로 기동하지 않습니다(`Settings.assert_safe_to_start`, API·전략 러너·Celery 워커 모두 호출).

## Consequences

- 업비트는 모의투자 서버가 없어 `paper` 모드에서는 실제 API 호출을 막고(`_require_live`), 시뮬레이션 체결 경로도 없으므로 `paper` 모드의 전략 러너는 코인 전략을 아예 평가하지 않습니다(`_runnable_asset_classes`). 즉 `paper`에서 코인 전략은 켜져 있어도 주문이 나가지 않습니다.

근거: `ARCHITECTURE.md` 5절 "모의/실전 분리"·"자격증명 분리", `5c7b2d2`, `7316246`·`0643f1e`(PR #6).
