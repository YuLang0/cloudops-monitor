#!/usr/bin/env bash
# 최초 배포.
#   1) .env 가 없으면 .env.example 로 만들고 비밀키를 생성한다(화면에 출력하지 않음).
#   2) 환경·설정 검사(check.sh)를 통과해야 진행한다.
#   3) 이미지를 빌드하고 HTTPS 구성으로 시작한 뒤, 내부·HTTPS 상태 확인이 통과할 때까지 기다린다.
# 이미 배포된 서버에서는 update.sh 를 쓴다. 이 스크립트는 데이터 볼륨을 지우지 않는다.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need docker
need curl

generate_secret() {
  local s
  while :; do
    s="$(head -c 48 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n')"
    # check.sh 가 '예시처럼 보이는 값'으로 거절하는 단어가 우연히 들어가면 다시 만든다
    [[ ${#s} -ge 64 && ! "$s" =~ (change|example|secret|password|test) ]] && break
  done
  printf '%s' "$s"
}

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  env_set CLOUDOPS_SECRET_KEY "$(generate_secret)"
  ok ".env 를 만들고 비밀키를 생성했습니다(값은 표시하지 않음, 권한 600)"
elif [[ -z "$(env_get CLOUDOPS_SECRET_KEY)" ]]; then
  env_set CLOUDOPS_SECRET_KEY "$(generate_secret)"
  ok "비어 있던 CLOUDOPS_SECRET_KEY 를 생성했습니다(값은 표시하지 않음)"
fi
chmod 600 "$ENV_FILE"

if [[ -z "$(env_get CLOUDOPS_DOMAIN)" ]]; then
  info ""
  info "다음 단계: .env 에 도메인을 적은 뒤 이 스크립트를 다시 실행하세요."
  info "  nano $ENV_FILE"
  info "  CLOUDOPS_DOMAIN=내이름.duckdns.org"
  exit 2
fi

if data_volume_exists && [[ "${1:-}" != --again ]]; then
  die "이미 배포된 서버입니다(데이터 볼륨이 있음). 코드·설정을 반영하려면 deploy/scripts/update.sh 를 쓰세요. (같은 과정을 다시 하려면 --again)"
fi

"$SCRIPT_DIR/check.sh"

domain="$(env_get CLOUDOPS_DOMAIN)"
info ""
info "== 이미지 빌드 (ARM 무료 서버에서 5~15분 걸릴 수 있음) =="
compose build --pull

info "== 시작 =="
compose up -d
wait_internal_health 180
wait_https_health "$domain" 300

info ""
ok "배포 완료: https://${domain}"
info "다음 순서:"
info "  1) 브라우저에서 https://${domain} 에 접속해 본인 계정을 만듭니다."
info "  2) .env 의 CLOUDOPS_ALLOW_REGISTRATION=false 로 바꾸고 deploy/scripts/update.sh 를 실행해 가입을 닫습니다."
info "  3) deploy/scripts/backup.sh 로 첫 백업을 만들고, docs/BACKUP_RESTORE.md 대로 PC 에 내려받습니다."
