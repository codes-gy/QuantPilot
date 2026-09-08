# QuantPilot

시장을 실시간 감시하고, 설정한 전략에 맞춰 자동으로 주식을 매매해 주는 스마트 자산 관리 앱 서비스입니다.

- 아키텍처와 데이터 흐름, 안전장치 설계: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- 백엔드(FastAPI): [`backend/`](./backend)
- 프론트엔드(Flutter): [`frontend/`](./frontend)

## 빠른 시작

```bash
cp .env.example .env
docker compose up --build
```

```bash
cd frontend
flutter pub get
flutter run --dart-define=API_BASE_URL=http://localhost:8000/api/v1 --dart-define=WS_URL=ws://localhost:8000/ws/live
```
