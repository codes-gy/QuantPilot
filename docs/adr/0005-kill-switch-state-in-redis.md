# 비상 정지 상태는 Redis 키 하나가 원본이고, 일일 손실 한도는 그 비상 정지를 켜는 것으로 구현한다

모든 주문 경로가 매번 확인하는 비상 정지 상태는 빠르게 읽혀야 해서 Postgres가 아니라 Redis 키 `kill_switch:global` 하나에 둡니다(`RedisKillSwitchRepository`). Postgres의 `kill_switch_audit_logs`는 언제 왜 켜졌는지를 남기는 감사 기록일 뿐 상태의 원본이 아닙니다. 계좌 전체 기준인 일일 손실 한도는 별도의 차단 경로를 만들지 않고, 한도를 넘는 순간 같은 비상 정지를 자동으로 켜서 기존 차단·미체결 주문 취소 경로를 그대로 탑니다(`RiskGuard.record_fill_pnl`). 일일 실현손익도 Redis에 한국 시간 날짜별 키로 쌓습니다.

## Consequences

- Redis가 안전 상태의 원본이므로 디스크에 저장해야 합니다(`appendonly yes`, `69ccf17`, PR #3). 저장하지 않으면 재시작만으로 비상 정지와 일일 손익이 사라져 매매가 다시 시작됩니다.
- 비상 정지는 신규 주문만 즉시 막고, 이미 접수된 미체결 주문은 체결 폴링 작업이 취소합니다(API로 켜면 즉시 한 번, 자동 발동이면 다음 10초 주기).

근거: `ARCHITECTURE.md` 5절 "비상 정지"·"일일 손실 한도"·"Kill switch 감사 로그", `570255f`, `1c8aed4`, `2bbab16`(PR #6).
