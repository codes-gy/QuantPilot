# 서버 배포 가이드 (네이버 클라우드 Micro, 메모리 1GB)

전체 흐름:

```
코드 push → GitHub Actions가 이미지 빌드 → ghcr.io에 업로드
                                              ↓
                         서버: deploy.sh가 이미지를 받아서 재시작
```

서버에서는 빌드하지 않습니다. 1GB 서버에서 `pip install`까지 하면 메모리가 부족해 멈출 수 있기 때문입니다.

> ⚠️ **PC와 서버에서 동시에 돌리지 마세요.** 같은 API 키로 전략이 두 곳에서 실행되면 주문이 두 번 나갑니다.
> 서버로 옮길 때는 PC의 Docker를 먼저 내립니다 (`docker compose down`, `-v`는 붙이지 않음).

---

## 1. 네이버 클라우드에서 서버 만들기

1. **Server → 서버 생성**
   - 이미지: **Ubuntu 22.04 또는 24.04**
   - 서버 타입: **Micro**
2. **공인 IP**를 할당하고 서버에 연결합니다. 이 IP를 업비트에 등록합니다.
3. **ACG(방화벽)** 인바운드 규칙:
   - `TCP 22` (SSH): **내 PC의 IP만** 허용합니다. `0.0.0.0/0`으로 열지 마세요.
   - 그 밖의 포트는 열지 않습니다. 8000(API)도 열지 않고 SSH 터널로 접속합니다.

## 2. 서버 초기 설정 (한 번만)

```bash
ssh <사용자>@<서버IP>
git clone https://github.com/codes-gy/QuantPilot.git ~/quantpilot
cd ~/quantpilot
sudo bash deploy/server-setup.sh   # 시간대, 스왑 2GB, Docker, 자동 보안 업데이트
exit                               # 다시 접속해야 docker 그룹이 적용됨
```

## 3. 배포

### 3-1. `.env` 옮기기 (PC에서 실행)

키가 들어 있는 파일이라 git에 올리지 않고 `scp`로 직접 복사합니다.

```powershell
cd A:\project\QuantPilot
scp .env <사용자>@<서버IP>:~/quantpilot/.env
```

서버의 `.env`는 PC와 같은 값을 그대로 씁니다. `DATABASE_URL`과 `REDIS_URL`도 compose 서비스 이름(`postgres`, `redis`) 기준이라 바꿀 필요가 없습니다.

### 3-2. 업비트 IP 등록

업비트 → 마이페이지 → Open API 관리에서 **서버 공인 IP를 허용 IP에 추가**합니다.
- PC IP는 서버가 정상 동작하는 걸 확인한 뒤 지웁니다.
- **출금 권한은 켜지 마세요.**

### 3-3. 실행

```bash
cd ~/quantpilot
bash deploy/deploy.sh
```

### 3-4. 로그인 계정 만들기

서버 DB는 새로 만들어지므로 계정을 다시 만듭니다.

```bash
docker compose -f docker-compose.prod.yml exec api python -m scripts.create_user <이메일>
```

전략도 서버에서 다시 등록합니다. 등록하면 일시정지 상태로 저장되고, 켜는 것은 직접 합니다.

## 4. 화면 접속 (SSH 터널)

API는 서버 자신(127.0.0.1)에만 열려 있습니다. PC에서 터널을 열면 PC의 `localhost:8000`이 서버 API로 연결됩니다.

```bash
ssh -N -L 8000:localhost:8000 <사용자>@<서버IP>
```

터널을 열어 둔 상태에서 PC의 화면(Flutter 웹이나 Windows 앱)을 평소처럼 실행합니다. 화면은 원래 `localhost:8000`을 보도록 되어 있어서 설정을 바꿀 필요가 없습니다.

## 5. 운영 명령

```bash
cd ~/quantpilot
C="docker compose -f docker-compose.prod.yml"

$C ps                                   # 상태
$C logs -f --tail=100 strategy-runner   # 로그 (ingestor, celery-worker 등)
docker stats --no-stream                # 메모리 사용량
bash deploy/deploy.sh                   # 최신 버전으로 업데이트
bash deploy/deploy.sh <커밋SHA>          # 그 커밋 시점 이미지로 되돌리기
$C down                                 # 정지 (-v는 DB와 비상 정지 상태까지 지우므로 쓰지 말 것)
```

- 서버가 재부팅되면 Docker가 컨테이너를 자동으로 다시 띄웁니다.
- 되돌리기 주의: DB 마이그레이션이 추가된 커밋보다 이전으로 되돌리면 옛 코드가 새 DB 구조와 맞지 않을 수 있습니다.

## 메모리 구성 (1GB)

| 서비스 | 상한 | 비고 |
|---|---|---|
| postgres | 192MB | `shared_buffers=32MB` 등 축소 |
| redis | 96MB | 디스크 저장(AOF) 유지, `maxmemory` 없음 |
| api | 192MB | `--reload` 없음 |
| ingestor / strategy-runner | 160MB씩 | |
| celery-worker | 256MB | 동시 실행 1개 |
| celery-beat | 128MB | |

- 상한의 합은 1GB보다 크지만 실제 사용량은 600MB 안팎입니다(개발 PC 측정 기준).
- 순간적으로 넘치는 부분은 스왑 2GB가 받아 줍니다.
- 한 서비스가 상한을 넘으면 그 컨테이너만 재시작됩니다.
