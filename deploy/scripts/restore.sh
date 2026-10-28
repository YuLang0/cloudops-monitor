#!/usr/bin/env bash
# 백업 복원.
#   deploy/scripts/restore.sh backups/cloudops-20261026T010203Z.db.gz
#   deploy/scripts/restore.sh <파일> --yes            # 확인 질문 생략
#   deploy/scripts/restore.sh <파일> --no-safety-backup  # 서비스가 죽어서 현재 데이터를 백업할 수 없을 때만
#
# 순서: 체크섬 확인 → 백업 파일 검증(서비스 정지 전) → 현재 데이터 안전 백업 → backend/frontend 정지
#       → 복원(백엔드가 멈춘 것을 잠금으로 확인한 뒤 교체) → 재시작 → 상태 확인
# 복원이 중간에 실패하면 기존 DB 는 바뀌지 않으며, 멈췄던 서비스를 다시 시작한다.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need docker
need gzip
require_env_file

src="${1:-}"
[[ -n "$src" && -f "$src" ]] || die "복원할 백업 파일을 지정하세요. 예: deploy/scripts/restore.sh backups/cloudops-…db.gz"
shift
assume_yes=0
safety_backup=1
for arg in "$@"; do
  case "$arg" in
    --yes) assume_yes=1 ;;
    --no-safety-backup) safety_backup=0 ;;
    *) die "알 수 없는 옵션: $arg" ;;
  esac
done
src="$(cd "$(dirname "$src")" && pwd)/$(basename "$src")"

# 1) 체크섬 (있으면)
if [[ -f "$src.sha256" ]]; then
  (cd "$(dirname "$src")" && sha256sum -c --status "$(basename "$src").sha256") || die "체크섬이 맞지 않습니다. 파일이 손상됐거나 다른 파일입니다"
  ok "체크섬 일치"
else
  warn "체크섬 파일(.sha256)이 없어 손상 여부를 미리 확인하지 못했습니다. 아래 무결성 검사는 진행합니다"
fi

# 2) 컨테이너가 읽을 수 있는 임시 폴더에 풀기 (컨테이너 사용자 uid 10001 이 읽어야 하므로 이 폴더만 755/644)
stage="$BACKUP_DIR/.restore-tmp"
rm -rf "$stage"
mkdir -p "$stage"
stopped=0
cleanup() {
  rm -rf "$stage"
  if ((stopped)); then
    warn "멈췄던 서비스를 다시 시작합니다"
    compose up -d backend frontend || true
  fi
}
trap cleanup EXIT
if [[ "$src" == *.gz ]]; then
  gzip -dc "$src" >"$stage/restore.db"
else
  cp "$src" "$stage/restore.db"
fi
chmod 755 "$stage"
chmod 644 "$stage/restore.db"

run_tool() {
  compose run --rm --no-deps -T -v "$stage:/restore:ro" backend python -m app.maintenance "$@"
}

# 3) 서비스를 멈추기 전에 백업 파일부터 검증
run_tool verify /restore/restore.db

if ((assume_yes == 0)); then
  read -r -p "현재 데이터를 이 백업으로 바꿉니다. 계속하려면 '복원' 을 입력하세요: " answer
  [[ "$answer" == 복원 ]] || die "취소했습니다"
fi

# 4) 현재 데이터 안전 백업
if ((safety_backup)); then
  if internal_health >/dev/null; then
    info "== 복원 전 현재 데이터 백업 =="
    "$SCRIPT_DIR/backup.sh"
  else
    die "서비스가 응답하지 않아 현재 데이터를 백업할 수 없습니다. 최근 백업이 있는지 확인한 뒤 --no-safety-backup 으로 다시 실행하세요"
  fi
fi

# 5) 정지 → 복원 → 시작
info "== 서비스 정지 =="
stopped=1
compose stop backend frontend
run_tool restore /restore/restore.db
compose up -d backend frontend
stopped=0
wait_internal_health 120
ok "복원 완료. 로그인해서 서버 목록과 장애 이력을 확인하세요"
