#!/usr/bin/env bash
# 새 Ubuntu 서버(네이버 클라우드 Micro, 메모리 1GB)를 QuantPilot 실행용으로 한 번 준비한다.
# 여러 번 실행해도 안전하다 (이미 된 단계는 건너뜀).
#
# 사용: sudo bash deploy/server-setup.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "root 권한이 필요합니다: sudo bash $0" >&2
  exit 1
fi

TARGET_USER="${SUDO_USER:-root}"

echo "== 1. 시간대: Asia/Seoul (일일 손실 한도가 한국 날짜 기준으로 초기화되도록)"
timedatectl set-timezone Asia/Seoul

echo "== 2. 스왑 2GB (메모리 1GB라 순간적으로 부족해도 프로세스가 죽지 않게)"
if ! swapon --show | grep -q /swapfile; then
  if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
# 메모리가 정말 부족할 때만 스왑을 쓰도록 (스왑은 디스크라 느리다)
echo 'vm.swappiness=10' > /etc/sysctl.d/99-quantpilot-swap.conf
sysctl -q --system

echo "== 3. Docker 설치"
if ! command -v docker >/dev/null; then
  apt-get update -q
  apt-get install -y -q ca-certificates curl git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  . /etc/os-release
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
systemctl enable --now docker
if [[ "$TARGET_USER" != "root" ]]; then
  usermod -aG docker "$TARGET_USER"
fi

echo "== 4. 보안 업데이트 자동 설치"
apt-get install -y -q unattended-upgrades
# 업데이트 때문에 서버가 멋대로 재부팅되지 않게 (재부팅은 직접 시간 정해서)
echo 'Unattended-Upgrade::Automatic-Reboot "false";' > /etc/apt/apt.conf.d/99-quantpilot-noreboot

echo
echo "완료. 메모리/스왑 상태:"
free -h
echo
echo "다음 단계: 로그아웃 후 다시 접속(docker 그룹 적용) → deploy/README.md의 '3. 배포'"
