#!/usr/bin/env bash
# SQLite 백업. 서비스를 멈추지 않고 SQLite 온라인 백업 API 로 한 시점의 일관된 사본을 만든다.
#   결과: backups/cloudops-<UTC시각>.db.gz  +  같은 이름의 .sha256
#   보관 개수: .env 의 CLOUDOPS_BACKUP_KEEP (기본 14). 오래된 것부터 지운다.
# 백업에는 비밀번호 해시와 Agent 키 해시가 들어 있으므로 권한 600 으로 저장한다.
# 같은 서버에만 두면 서버를 잃을 때 함께 잃는다 → docs/BACKUP_RESTORE.md 대로 PC 에 내려받는다.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need docker
need gzip
need sha256sum
require_env_file

keep="$(env_get CLOUDOPS_BACKUP_KEEP)"
keep="${keep:-14}"
[[ "$keep" =~ ^[1-9][0-9]*$ ]] || die "CLOUDOPS_BACKUP_KEEP 는 1 이상의 정수여야 합니다"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

name="cloudops-$(date -u +%Y%m%dT%H%M%SZ).db"
inner="/app/data/backup-tmp/$name"
cleanup_inner() { compose exec -T backend rm -f "$inner" "$inner.partial" >/dev/null 2>&1 || true; }
trap 'cleanup_inner; rm -f "$BACKUP_DIR/$name" "$BACKUP_DIR/$name.gz" "$BACKUP_DIR/$name.gz.sha256"' EXIT

# 1) 컨테이너 안에서 일관된 백업 + 무결성 검사 (출력은 테이블별 행 수뿐)
compose exec -T backend python -m app.maintenance backup "$inner"
# 2) 호스트로 복사
compose cp "backend:$inner" "$BACKUP_DIR/$name" >/dev/null
cleanup_inner
# 3) 압축 + 체크섬 (내려받은 뒤 손상 여부를 확인할 수 있게)
gzip -9 "$BACKUP_DIR/$name"
(cd "$BACKUP_DIR" && sha256sum "$name.gz" >"$name.gz.sha256")
chmod 600 "$BACKUP_DIR/$name.gz" "$BACKUP_DIR/$name.gz.sha256"
trap - EXIT

ok "백업 저장: $BACKUP_DIR/$name.gz ($(du -h "$BACKUP_DIR/$name.gz" | cut -f1))"

# 4) 보관 개수 초과분 삭제 (백업 파일만, 오래된 순)
mapfile -t old < <(ls -1t "$BACKUP_DIR"/cloudops-*.db.gz 2>/dev/null | tail -n +"$((keep + 1))")
for f in "${old[@]}"; do
  rm -f -- "$f" "$f.sha256"
done
((${#old[@]} == 0)) || info "오래된 백업 ${#old[@]}개 정리 (최근 ${keep}개 보관)"
