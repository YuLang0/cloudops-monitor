#!/usr/bin/env bash
# 배포 스크립트 공통 함수. 직접 실행하지 않고 다른 스크립트가 source 한다.
#
# 원칙
#  - 실패하면 즉시 중단한다(set -Eeuo pipefail + 오류 위치 출력).
#  - 비밀값(비밀키·토큰·비밀번호)은 절대 화면에 출력하지 않는다. 길이나 "설정됨"만 보여 준다.
#  - 데이터 볼륨을 지우는 명령(docker compose down -v, docker volume rm)은 어디에도 쓰지 않는다.

set -Eeuo pipefail
umask 077 # 이 스크립트들이 만드는 파일(.env, 백업)은 기본적으로 본인만 읽을 수 있게

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$ROOT/.env"
BACKUP_DIR="${CLOUDOPS_BACKUP_DIR:-$ROOT/backups}"

if [[ -t 1 ]]; then
  C_OK=$'\e[32m' C_WARN=$'\e[33m' C_ERR=$'\e[31m' C_DIM=$'\e[2m' C_END=$'\e[0m'
else
  C_OK="" C_WARN="" C_ERR="" C_DIM="" C_END=""
fi

info() { printf '%s\n' "$*"; }
ok() { printf '%s[ OK ]%s %s\n' "$C_OK" "$C_END" "$*"; }
warn() { printf '%s[경고]%s %s\n' "$C_WARN" "$C_END" "$*" >&2; }
err() { printf '%s[오류]%s %s\n' "$C_ERR" "$C_END" "$*" >&2; }
die() {
  err "$*"
  exit 1
}

_on_error() {
  local code=$? line=$1
  err "명령이 실패해 중단했습니다 (${BASH_SOURCE[1]##*/}:$line, 종료코드 $code)"
}
trap '_on_error $LINENO' ERR

need() {
  command -v "$1" >/dev/null 2>&1 || die "'$1' 명령이 없습니다. deploy/scripts/setup-server.sh 로 서버를 먼저 준비하세요."
}

# .env 에서 값 하나를 읽는다. source 하지 않는다(.env 안의 내용이 명령으로 실행되는 일을 막기 위해).
# 값은 호출한 쪽의 변수로만 쓰고, 출력하지 않는다.
env_get() {
  local key=$1 line
  [[ -f "$ENV_FILE" ]] || return 0
  line="$(grep -E "^[[:space:]]*${key}=" "$ENV_FILE" | tail -n 1 || true)"
  line="${line#*=}"
  line="${line%$'\r'}"
  # 앞뒤 따옴표 제거
  if [[ ${#line} -ge 2 && ( ${line:0:1} == '"' && ${line: -1} == '"' || ${line:0:1} == "'" && ${line: -1} == "'" ) ]]; then
    line="${line:1:${#line}-2}"
  fi
  printf '%s' "$line"
}

# .env 의 KEY 값을 바꾸거나 추가한다. 값은 출력하지 않는다.
env_set() {
  local key=$1 value=$2 tmp
  tmp="$(mktemp "$ROOT/.env.XXXXXX")"
  if grep -qE "^[[:space:]]*${key}=" "$ENV_FILE"; then
    awk -v k="$key" -v v="$value" 'BEGIN{done=0} $0 ~ "^[[:space:]]*"k"=" && !done {print k"="v; done=1; next} {print}' "$ENV_FILE" >"$tmp"
  else
    cat "$ENV_FILE" >"$tmp"
    printf '%s=%s\n' "$key" "$value" >>"$tmp"
  fi
  chmod 600 "$tmp"
  mv "$tmp" "$ENV_FILE"
}

# 서버 배포는 항상 HTTPS 구성(Caddy)까지 함께 사용한다.
compose() {
  docker compose \
    --project-directory "$ROOT" \
    --env-file "$ENV_FILE" \
    -f "$ROOT/docker-compose.yml" \
    -f "$ROOT/docker-compose.https.yml" \
    "$@"
}

# 컨테이너 안에서 nginx → FastAPI → DB 경로 전체를 확인한다(인터넷을 거치지 않음).
internal_health() {
  compose exec -T frontend wget -q -T 5 -O - http://127.0.0.1/api/v1/health 2>/dev/null
}

wait_internal_health() {
  local timeout=${1:-120} waited=0
  info "${C_DIM}내부 상태 확인 대기(최대 ${timeout}초)…${C_END}"
  until internal_health >/dev/null; do
    sleep 3
    waited=$((waited + 3))
    if ((waited >= timeout)); then
      err "내부 상태 확인이 ${timeout}초 안에 성공하지 못했습니다. 'deploy/scripts/status.sh' 와 'docker compose logs backend' 를 확인하세요."
      return 1
    fi
  done
  ok "내부 상태 확인 통과 (nginx → FastAPI → DB)"
}

wait_https_health() {
  local domain=$1 timeout=${2:-180} waited=0
  info "${C_DIM}HTTPS 확인 대기(인증서 발급 포함, 최대 ${timeout}초)…${C_END}"
  until curl -fsS --max-time 10 "https://${domain}/api/v1/health" >/dev/null 2>&1; do
    sleep 5
    waited=$((waited + 5))
    if ((waited >= timeout)); then
      err "https://${domain} 에 접속하지 못했습니다. DNS·방화벽(80/443)·'docker compose logs caddy' 를 확인하세요."
      return 1
    fi
  done
  ok "HTTPS 확인 통과: https://${domain}"
}

data_volume_exists() {
  docker volume inspect cloudops-monitor_cloudops-data >/dev/null 2>&1
}

require_env_file() {
  [[ -f "$ENV_FILE" ]] || die ".env 가 없습니다. 먼저 deploy/scripts/deploy.sh 를 실행하면 만들어 줍니다."
}
