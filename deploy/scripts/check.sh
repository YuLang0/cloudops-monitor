#!/usr/bin/env bash
# 배포 전 환경·필수 설정 검사. 문제를 모두 모아 보여 주고, 오류가 하나라도 있으면 종료코드 1.
# 비밀값은 출력하지 않는다(길이·설정 여부만).
#
#   deploy/scripts/check.sh            # 서버 환경 + .env 검사
#   deploy/scripts/check.sh --env-only # .env 만 검사(Docker 가 없는 PC 에서 미리 확인할 때)
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

ENV_ONLY=0
[[ "${1:-}" == "--env-only" ]] && ENV_ONLY=1

errors=0
warnings=0
fail() {
  err "$*"
  errors=$((errors + 1))
}
caution() {
  warn "$*"
  warnings=$((warnings + 1))
}

PY=python3
command -v python3 >/dev/null 2>&1 || PY=python

# ---------------------------------------------------------------- 서버 환경
if ((ENV_ONLY == 0)); then
  info "== 서버 환경 =="
  if [[ -r /etc/os-release ]]; then
    os_id="$(. /etc/os-release && printf '%s' "${ID:-}")"
    os_ver="$(. /etc/os-release && printf '%s' "${VERSION:-}")"
    if [[ "$os_id" == ubuntu && "$os_ver" == *LTS* ]]; then
      ok "운영체제: Ubuntu $os_ver"
    else
      caution "Ubuntu LTS 가 아닙니다 ($os_id $os_ver). 이 스크립트는 Ubuntu LTS 기준으로 작성됐습니다."
    fi
  else
    caution "운영체제를 확인할 수 없습니다(/etc/os-release 없음)"
  fi

  arch="$(uname -m)"
  case "$arch" in
    aarch64 | arm64) ok "CPU 구조: ARM64 ($arch) — Ampere A1. 모든 이미지·의존성이 ARM64 를 지원합니다" ;;
    x86_64 | amd64) ok "CPU 구조: AMD64 ($arch)" ;;
    *) fail "지원하지 않는 CPU 구조: $arch (ARM64 또는 AMD64 필요)" ;;
  esac

  if [[ -r /proc/meminfo ]]; then
    mem_mb=$(awk '/^MemTotal:/{print int($2/1024)}' /proc/meminfo)
    swap_mb=$(awk '/^SwapTotal:/{print int($2/1024)}' /proc/meminfo)
    if ((mem_mb + swap_mb < 1900)); then
      caution "메모리 ${mem_mb}MB + 스왑 ${swap_mb}MB. 프론트엔드 빌드 중 메모리가 부족할 수 있습니다. 'sudo deploy/scripts/setup-server.sh' 가 스왑을 만들어 줍니다."
    else
      ok "메모리 ${mem_mb}MB, 스왑 ${swap_mb}MB"
    fi
  fi

  avail_mb=$(df -Pm "$ROOT" | awk 'NR==2{print $4}')
  if ((avail_mb < 3000)); then
    fail "디스크 여유 공간 ${avail_mb}MB — 이미지 빌드에 최소 3GB 가 필요합니다"
  elif ((avail_mb < 8000)); then
    caution "디스크 여유 공간 ${avail_mb}MB — 백업을 오래 쌓으면 부족해질 수 있습니다"
  else
    ok "디스크 여유 공간 ${avail_mb}MB"
  fi

  if ! command -v docker >/dev/null 2>&1; then
    fail "Docker 가 없습니다. 'sudo deploy/scripts/setup-server.sh' 를 먼저 실행하세요"
  elif ! docker info >/dev/null 2>&1; then
    fail "Docker 에 접근할 수 없습니다. setup-server.sh 실행 후 한 번 로그아웃했다가 다시 SSH 로 접속하세요(docker 그룹 적용)"
  else
    cv="$(docker compose version --short 2>/dev/null || true)"
    cv="${cv#v}"
    if [[ -z "$cv" ]]; then
      fail "docker compose 플러그인이 없습니다"
    elif [[ "$(printf '%s\n%s\n' 2.24.0 "$cv" | sort -V | head -n 1)" != 2.24.0 ]]; then
      fail "Docker Compose $cv — 2.24 이상이 필요합니다(docker-compose.https.yml 의 !reset 사용)"
    else
      ok "Docker Compose $cv"
    fi
    if command -v systemctl >/dev/null 2>&1; then
      if [[ "$(systemctl is-enabled docker 2>/dev/null || true)" == enabled ]]; then
        ok "Docker 가 부팅 시 자동 시작됨 (컨테이너는 restart: unless-stopped 로 함께 복구)"
      else
        fail "Docker 가 부팅 시 자동 시작되지 않습니다: sudo systemctl enable --now docker"
      fi
    fi
  fi

  if command -v ss >/dev/null 2>&1; then
    for port in 80 443; do
      holder="$(ss -Hltnp "sport = :$port" 2>/dev/null | head -n 1 || true)"
      if [[ -n "$holder" && "$holder" != *docker-proxy* ]]; then
        fail "포트 $port 를 다른 프로그램이 쓰고 있습니다(웹서버가 이미 설치돼 있나요?)"
      fi
    done
  fi
fi

# ---------------------------------------------------------------- .env
info "== 설정 파일(.env) =="
if [[ ! -f "$ENV_FILE" ]]; then
  fail ".env 가 없습니다. deploy/scripts/deploy.sh 를 실행하면 .env.example 로부터 만들고 비밀키도 생성합니다"
else
  perm="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo unknown)"
  if [[ "$perm" == 600 || "$perm" == 400 ]]; then
    ok ".env 권한 $perm (본인만 읽기)"
  elif [[ "$perm" == unknown ]]; then
    caution ".env 권한을 확인할 수 없습니다"
  else
    fail ".env 권한이 $perm 입니다. 다른 사용자가 비밀키를 읽을 수 있습니다: chmod 600 .env"
  fi

  secret="$(env_get CLOUDOPS_SECRET_KEY)"
  if [[ -z "$secret" ]]; then
    fail "CLOUDOPS_SECRET_KEY 가 비어 있습니다(deploy.sh 가 자동 생성합니다). 비어 있으면 백엔드가 시작을 거부합니다"
  elif ((${#secret} < 32)); then
    fail "CLOUDOPS_SECRET_KEY 가 ${#secret}자입니다. 32자 이상이어야 합니다"
  elif [[ "$secret" =~ (change|example|secret|password|test) ]]; then
    fail "CLOUDOPS_SECRET_KEY 가 예시 문자열처럼 보입니다. 무작위 값으로 바꾸세요"
  else
    ok "CLOUDOPS_SECRET_KEY 설정됨 (${#secret}자, 값은 표시하지 않음)"
  fi
  unset secret

  domain="$(env_get CLOUDOPS_DOMAIN)"
  if [[ -z "$domain" ]]; then
    fail "CLOUDOPS_DOMAIN 이 비어 있습니다. 예: myname.duckdns.org (docs/FREE_DEPLOY.md 4장)"
  elif [[ ! "$domain" =~ ^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$ ]]; then
    fail "CLOUDOPS_DOMAIN 형식이 올바르지 않습니다(소문자 도메인 이름만, https:// 나 / 없이)"
  elif [[ "$domain" == *example.com ]]; then
    fail "CLOUDOPS_DOMAIN 이 예시 값(example.com)입니다"
  else
    ok "CLOUDOPS_DOMAIN: $domain"
  fi

  bind="$(env_get CLOUDOPS_BIND)"
  if [[ -n "$bind" && "$bind" != 127.0.0.1 ]]; then
    fail "CLOUDOPS_BIND=$bind — 서버에서는 HTTP 포트를 외부에 열지 않습니다. 이 줄을 지우거나 127.0.0.1 로 두세요"
  fi

  cors="$(env_get CLOUDOPS_CORS_ORIGINS)"
  if [[ -n "$cors" ]]; then
    IFS=',' read -r -a origins <<<"$cors"
    for o in "${origins[@]}"; do
      o="${o// /}"
      [[ "$o" == https://* ]] || fail "CLOUDOPS_CORS_ORIGINS 에 https 가 아닌 출처가 있습니다: $o"
      [[ "$o" == *"*"* ]] && fail "CLOUDOPS_CORS_ORIGINS 에 와일드카드(*)는 쓸 수 없습니다"
    done
  else
    ok "허용 Origin: 같은 도메인만 (CLOUDOPS_CORS_ORIGINS 비어 있음 — 기본 구성에 맞음)"
  fi

  for key in CLOUDOPS_RETENTION_DAYS CLOUDOPS_INCIDENT_RETENTION_DAYS CLOUDOPS_BACKUP_KEEP; do
    v="$(env_get "$key")"
    if [[ -n "$v" && ! "$v" =~ ^[1-9][0-9]*$ ]]; then
      fail "$key 는 1 이상의 정수여야 합니다"
    fi
  done
  ok "측정값 보관 $(env_get CLOUDOPS_RETENTION_DAYS | grep . || echo 7)일, 해결된 장애 보관 $(env_get CLOUDOPS_INCIDENT_RETENTION_DAYS | grep . || echo 365)일 (그 이전 기록은 1시간마다 자동 삭제)"

  if [[ "$(env_get CLOUDOPS_ALLOW_REGISTRATION)" != false ]]; then
    caution "회원가입이 열려 있습니다. 본인 계정을 만든 뒤 CLOUDOPS_ALLOW_REGISTRATION=false 로 바꾸고 update.sh 를 실행하세요"
  fi

  cookie="$(env_get CLOUDOPS_COOKIE_SECURE)"
  if [[ "$cookie" == false ]]; then
    ok "쿠키: .env 값과 상관없이 HTTPS 구성(docker-compose.https.yml)이 Secure 쿠키를 강제합니다"
  fi

  # 고정 주소 일관성: 백엔드는 nginx 를, nginx 는 Caddy 를 신뢰한다
  if ! "$PY" - "$(env_get CLOUDOPS_APP_SUBNET)" "$(env_get CLOUDOPS_NGINX_IP)" "$(env_get CLOUDOPS_EDGE_SUBNET)" "$(env_get CLOUDOPS_CADDY_IP)" <<'PY'
import ipaddress, sys
app, nginx, edge, caddy = (a or d for a, d in zip(sys.argv[1:], ("172.31.0.0/24", "172.31.0.10", "172.30.0.0/24", "172.30.0.2")))
try:
    app_n, edge_n = ipaddress.ip_network(app), ipaddress.ip_network(edge)
    nginx_ip, caddy_ip = ipaddress.ip_address(nginx), ipaddress.ip_address(caddy)
except ValueError as e:
    print(f"주소 형식 오류: {e}"); sys.exit(1)
problems = []
if nginx_ip not in app_n: problems.append("CLOUDOPS_NGINX_IP 가 CLOUDOPS_APP_SUBNET 밖에 있습니다")
if caddy_ip not in edge_n: problems.append("CLOUDOPS_CADDY_IP 가 CLOUDOPS_EDGE_SUBNET 밖에 있습니다")
if app_n.overlaps(edge_n): problems.append("두 서브넷이 겹칩니다")
for ip, n in ((nginx_ip, app_n), (caddy_ip, edge_n)):
    if ip in (n.network_address, n.network_address + 1, n.broadcast_address):
        problems.append(f"{ip} 는 네트워크·게이트웨이·브로드캐스트 주소라 쓸 수 없습니다")
print("; ".join(problems)); sys.exit(1 if problems else 0)
PY
  then
    fail "내부 네트워크 주소 설정이 맞지 않습니다(위 메시지 참고)"
  else
    ok "신뢰 프록시 주소: 백엔드는 nginx 한 주소만, nginx 는 Caddy 한 주소만 신뢰"
  fi
fi

# ---------------------------------------------------------------- DNS
if ((ENV_ONLY == 0)) && [[ -n "${domain:-}" ]]; then
  info "== DNS =="
  resolved="$("$PY" -c 'import socket,sys
try: print(" ".join(sorted({a[4][0] for a in socket.getaddrinfo(sys.argv[1], 443, socket.AF_INET)})))
except OSError: pass' "$domain")"
  public_ip="$(curl -fsS --max-time 8 https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || true)"
  if [[ -z "$resolved" ]]; then
    fail "$domain 의 DNS 주소를 찾지 못했습니다. DuckDNS 에 이 서버의 공인 IP 를 등록했는지 확인하세요"
  elif [[ -z "$public_ip" ]]; then
    caution "이 서버의 공인 IP 를 확인하지 못했습니다. $domain → $resolved 가 서버 주소인지 직접 확인하세요"
  elif [[ " $resolved " == *" $public_ip "* ]]; then
    ok "$domain → $public_ip (이 서버)"
  else
    fail "$domain 은 $resolved 를 가리키지만 이 서버의 공인 IP 는 $public_ip 입니다. 이대로는 인증서를 발급받을 수 없습니다"
  fi
fi

info ""
if ((errors > 0)); then
  err "오류 ${errors}개, 경고 ${warnings}개 — 오류를 고친 뒤 다시 실행하세요"
  exit 1
fi
ok "검사 통과 (경고 ${warnings}개)"
