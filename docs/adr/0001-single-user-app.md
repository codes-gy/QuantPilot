# 다중 사용자 SaaS가 아니라 1인용 앱으로 만든다

QuantPilot은 한 사람이 자기 계좌로 쓰는 앱이라, 데이터에 소유자 개념을 두지 않았습니다. 주문·포지션·전략·비상 정지·일일 손익은 모두 계좌 하나에 대한 전역 상태입니다(`positions.symbol`이 전역 unique, 비상 정지는 Redis 키 `kill_switch:global` 하나). 공개 회원가입은 없고 계정은 CLI(`scripts/create_user.py`)로만 만듭니다. 인증은 앱 접근 제어 수준입니다. 나중에 여러 사용자를 받으려면 모든 테이블과 Redis 키에 소유자를 넣는 큰 변경이 필요합니다.

근거: `ARCHITECTURE.md` 1절, `backend/README.md` "사용자 계정 생성", `backend/app/features/account/models.py`, `backend/app/features/trading/models.py`, `09a4859`.
