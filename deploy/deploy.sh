#!/usr/bin/env bash
# 서버에서 최신 코드/이미지로 업데이트하고 재시작한다.
#
# 사용: bash deploy/deploy.sh            (최신 main)
#       bash deploy/deploy.sh <커밋SHA>   (그 시점 이미지로 되돌리기)
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f docker-compose.prod.yml"

if [[ ! -f .env ]]; then
  echo ".env가 없습니다. PC의 .env를 이 폴더로 복사하세요 (deploy/README.md 참고)." >&2
  exit 1
fi
if [[ "$(stat -c %a .env)" != "600" ]]; then
  chmod 600 .env
fi

if [[ $# -ge 1 ]]; then
  export QUANTPILOT_IMAGE="ghcr.io/codes-gy/quantpilot-backend:$1"
  echo "== 이미지 고정: $QUANTPILOT_IMAGE"
else
  echo "== 코드 업데이트 (compose 파일 등)"
  git pull --ff-only
fi

echo "== 이미지 받기"
$COMPOSE pull

echo "== 재시작"
$COMPOSE up -d --remove-orphans

echo "== 오래된 이미지 정리 (디스크 절약)"
docker image prune -f >/dev/null

$COMPOSE ps
echo
echo "로그 보기: $COMPOSE logs -f --tail=100"
