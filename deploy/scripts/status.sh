#!/usr/bin/env bash
# 상태 확인: 컨테이너, 내부/HTTPS 상태, 인증서 만료일, DB·디스크·메모리, 최근 백업.
# 문제가 있으면 종료코드 1 (cron 으로 돌려 알림을 붙이기 쉽게).
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need docker
require_env_file
problems=0
domain="$(env_get CLOUDOPS_DOMAIN)"

info "== 컨테이너 =="
compose ps --format 'table {{.Service}}\t{{.Status}}'
for svc in backend frontend caddy; do
  cid="$(compose ps -q "$svc" 2>/dev/null || true)"
  if [[ -z "$cid" ]]; then
    err "$svc 컨테이너가 없습니다"
    problems=$((problems + 1))
    continue
  fi
  restarts="$(docker inspect -f '{{.RestartCount}}' "$cid")"
  ((restarts > 0)) && warn "$svc 가 ${restarts}번 재시작됐습니다: docker compose logs $svc"
done

info "== 상태 확인 =="
if health="$(internal_health)"; then
  ok "내부: $health"
  [[ "$health" == *'"background":"running"'* ]] || { warn "백그라운드 작업(연결 끊김 감시 등)이 이 백엔드에서 실행 중이 아닙니다"; problems=$((problems + 1)); }
else
  err "내부 상태 확인 실패 (nginx → FastAPI → DB)"
  problems=$((problems + 1))
fi
if [[ -n "$domain" ]]; then
  if curl -fsS --max-time 10 "https://${domain}/api/v1/health" >/dev/null 2>&1; then
    ok "HTTPS: https://${domain}"
  else
    err "HTTPS 접속 실패: https://${domain}"
    problems=$((problems + 1))
  fi
  if command -v openssl >/dev/null 2>&1; then
    end="$(echo | openssl s_client -servername "$domain" -connect "${domain}:443" 2>/dev/null | openssl x509 -noout -enddate 2>/dev/null | cut -d= -f2 || true)"
    [[ -n "$end" ]] && ok "인증서 만료: $end (Caddy 가 만료 30일 전쯤 자동 갱신)"
  fi
  code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "http://${domain}/api/v1/health" || true)"
  if [[ "$code" == 30* ]]; then
    ok "HTTP 요청은 HTTPS 로 넘어감($code) — 평문으로 처리되지 않음"
  elif [[ -n "$code" && "$code" != 000 ]]; then
    err "HTTP 요청이 HTTPS 로 넘어가지 않습니다(응답 $code)"
    problems=$((problems + 1))
  fi
fi

info "== 저장 공간 =="
compose exec -T backend sh -c 'du -ch /app/data/cloudops.db* 2>/dev/null | tail -n 1' | sed 's/^/DB 크기: /' || true
df -h "$ROOT" | awk 'NR==2{print "디스크: 사용 "$3" / 전체 "$2" (여유 "$4")"}'
docker system df --format 'table {{.Type}}\t{{.Size}}\t{{.Reclaimable}}' 2>/dev/null || true
command -v free >/dev/null 2>&1 && free -h | awk 'NR<=3'

info "== 백업 =="
latest="$(ls -1t "$BACKUP_DIR"/cloudops-*.db.gz 2>/dev/null | head -n 1 || true)"
if [[ -z "$latest" ]]; then
  warn "백업이 없습니다: deploy/scripts/backup.sh"
else
  age_h=$((($(date +%s) - $(stat -c %Y "$latest")) / 3600))
  ok "최근 백업: $(basename "$latest") (${age_h}시간 전, 총 $(ls -1 "$BACKUP_DIR"/cloudops-*.db.gz | wc -l)개)"
  ((age_h > 48)) && warn "최근 백업이 이틀보다 오래됐습니다"
fi

((problems == 0)) || exit 1
