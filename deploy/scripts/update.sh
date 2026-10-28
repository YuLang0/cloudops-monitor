#!/usr/bin/env bash
# 업데이트: 새 코드나 .env 변경을 반영한다.
#   1) 설정 검사 → 2) 백업 → 3) 이미지 다시 빌드(베이스 이미지 보안 패치 포함) → 4) 재시작 → 5) 상태 확인
# 데이터 볼륨은 그대로 유지한다. 실패하면 직전 백업으로 되돌리는 명령을 알려 준다.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need docker
need curl
require_env_file
data_volume_exists || die "아직 배포되지 않았습니다. 먼저 deploy/scripts/deploy.sh 를 실행하세요."

"$SCRIPT_DIR/check.sh"
domain="$(env_get CLOUDOPS_DOMAIN)"

info "== 업데이트 전 백업 =="
if internal_health >/dev/null; then
  "$SCRIPT_DIR/backup.sh"
  last_backup="$(ls -1t "$BACKUP_DIR"/cloudops-*.db.gz 2>/dev/null | head -n 1)"
else
  [[ "${1:-}" == --skip-backup ]] || die "서비스가 응답하지 않아 백업할 수 없습니다. 그래도 진행하려면 --skip-backup (최근 백업이 있는지 먼저 확인)"
  warn "백업 없이 진행합니다"
  last_backup=""
fi

info "== 이미지 빌드 =="
compose build --pull

info "== 재시작 =="
compose up -d
if ! wait_internal_health 180 || ! wait_https_health "$domain" 180; then
  err "업데이트 후 상태 확인에 실패했습니다."
  if [[ -n "$last_backup" ]]; then
    info "데이터를 업데이트 전으로 되돌리려면: deploy/scripts/restore.sh $last_backup"
  fi
  exit 1
fi

# 이전 빌드의 이름 없는 이미지 정리(디스크 절약). 볼륨은 건드리지 않는다.
docker image prune -f >/dev/null
ok "업데이트 완료"
