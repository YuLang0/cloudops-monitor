#!/usr/bin/env bash
# 새 Ubuntu LTS 서버(Oracle Cloud Always Free) 준비. 한 번만 sudo 로 실행한다.
#   sudo deploy/scripts/setup-server.sh
#
# 하는 일
#   1) Docker Engine + Compose 플러그인 설치 (docs.docker.com 의 공식 apt 저장소)
#   2) Docker 부팅 시 자동 시작, 현재 사용자를 docker 그룹에 추가
#   3) 서버 안 방화벽(iptables)에 80/443 허용 추가 — Oracle Ubuntu 이미지는 22번 외에는 기본으로 막혀 있다
#   4) 메모리가 2GB 미만이면 2GB 스왑 파일 생성 (AMD Micro 1GB 서버에서 빌드가 멈추지 않게)
#   5) 보안 업데이트 자동 설치(unattended-upgrades) 켜기
# 하지 않는 일: SSH 설정 변경(잘못되면 접속이 끊긴다), 22번 포트 제한(Oracle 콘솔의 Security List 에서 한다)
set -Eeuo pipefail
trap 'echo "[오류] setup-server.sh ${LINENO}번째 줄에서 실패했습니다" >&2' ERR

[[ $EUID -eq 0 ]] || { echo "sudo 로 실행하세요: sudo $0" >&2; exit 1; }
. /etc/os-release
[[ "${ID:-}" == ubuntu ]] || { echo "Ubuntu 전용 스크립트입니다 (현재: ${ID:-unknown})" >&2; exit 1; }
target_user="${SUDO_USER:-ubuntu}"
export DEBIAN_FRONTEND=noninteractive

echo "== 1) Docker 설치 =="
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  apt-get update -y
  apt-get install -y ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "이미 설치됨: $(docker --version)"
fi
apt-get install -y openssl unzip gzip >/dev/null

echo "== 2) Docker 자동 시작 · docker 그룹 =="
systemctl enable --now docker
if ! id -nG "$target_user" | tr ' ' '\n' | grep -qx docker; then
  usermod -aG docker "$target_user"
  echo "$target_user 를 docker 그룹에 추가했습니다. 적용하려면 SSH 를 끊었다가 다시 접속하세요."
fi

echo "== 3) 서버 방화벽: 80/443 허용 =="
# Oracle 의 Ubuntu 이미지에는 22번만 열고 나머지를 REJECT 하는 iptables 규칙이 들어 있다.
# REJECT 규칙보다 앞에 80/443 허용을 넣는다. (Oracle 콘솔의 Security List 에서도 따로 열어야 한다)
if command -v iptables >/dev/null 2>&1; then
  for port in 443 80; do
    if iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
      echo "포트 $port: 이미 허용됨"
      continue
    fi
    reject_line="$(iptables -L INPUT --line-numbers -n | awk '$2=="REJECT"{print $1; exit}')"
    if [[ -n "$reject_line" ]]; then
      iptables -I INPUT "$reject_line" -p tcp -m state --state NEW --dport "$port" -j ACCEPT
    else
      iptables -A INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT
    fi
    echo "포트 $port: 허용 추가"
  done
  if command -v netfilter-persistent >/dev/null 2>&1; then
    netfilter-persistent save >/dev/null
    echo "재부팅 후에도 유지되도록 저장했습니다"
  else
    echo "[경고] netfilter-persistent 가 없어 재부팅하면 위 규칙이 사라질 수 있습니다: sudo apt-get install -y iptables-persistent" >&2
  fi
fi
if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null
  ufw allow 443/tcp >/dev/null
  echo "ufw 에도 80/443 허용 추가"
fi

echo "== 4) 스왑 =="
mem_mb=$(awk '/^MemTotal:/{print int($2/1024)}' /proc/meminfo)
swap_mb=$(awk '/^SwapTotal:/{print int($2/1024)}' /proc/meminfo)
if ((mem_mb < 2000 && swap_mb < 1000)); then
  if [[ ! -f /swapfile ]]; then
    fallocate -l 2G /swapfile
    chmod 600 /swapfile
    mkswap /swapfile >/dev/null
  fi
  swapon /swapfile 2>/dev/null || true
  grep -q '^/swapfile ' /etc/fstab || echo '/swapfile none swap sw 0 0' >>/etc/fstab
  echo "2GB 스왑 사용 (메모리 ${mem_mb}MB)"
else
  echo "필요 없음 (메모리 ${mem_mb}MB, 스왑 ${swap_mb}MB)"
fi

echo "== 5) 보안 업데이트 자동 설치 =="
apt-get install -y unattended-upgrades >/dev/null
systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
echo "unattended-upgrades 사용"

echo ""
echo "완료. 다음 순서:"
echo "  1) exit 로 SSH 를 끊고 다시 접속 (docker 그룹 적용)"
echo "  2) cd ~/cloudops-monitor && deploy/scripts/deploy.sh"
