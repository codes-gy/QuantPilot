# QuantPilot Frontend (Flutter)

실시간 시세 감시, 전략 관리, 주문 내역, 비상 정지 스위치를 제공하는 모바일 앱.
폴더 구조와 각 레이어의 역할은 저장소 루트의 `ARCHITECTURE.md`를 참고하세요.

## 실행

```bash
flutter pub get
flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1 --dart-define=WS_URL=ws://localhost:8000/ws/live
```

## 구조

```
lib/
  core/        # 네트워크 클라이언트, 테마, DI(Riverpod provider root), 상수
  features/    # feature별 data / domain / presentation 3계층
```
