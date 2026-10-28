#!/usr/bin/env bash
# DuckDNS 주소를 이 서버의 현재 공인 IP 로 갱신한다(선택).
# Oracle 의 임시(ephemeral) 공인 IP 는 인스턴스를 지우기 전까지 보통 바뀌지 않으므로, 최초 1회만 실행해도 된다.
# 주기적으로 갱신하려면 crontab -e 에:
#   */30 * * * * /home/ubuntu/cloudops-monitor/deploy/scripts/duckdns-update.sh >/dev/null 2>&1
#
# 필요한 .env 값: CLOUDOPS_DOMAIN=내이름.duckdns.org, CLOUDOPS_DUCKDNS_TOKEN=<DuckDNS 화면의 token>
# 토큰은 명령행 인자로 넘기지 않는다(같은 서버의 다른 사용자가 ps 로 볼 수 있음). curl 설정을 표준입력으로 전달한다.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

need curl
require_env_file
domain="$(env_get CLOUDOPS_DOMAIN)"
[[ "$domain" =~ ^([a-z0-9-]+)\.duckdns\.org$ ]] || die "CLOUDOPS_DOMAIN 이 '<이름>.duckdns.org' 형식이 아닙니다"
sub="${BASH_REMATCH[1]}"
token="$(env_get CLOUDOPS_DUCKDNS_TOKEN)"
[[ "$token" =~ ^[0-9a-fA-F-]{36}$ ]] || die "CLOUDOPS_DUCKDNS_TOKEN 이 비어 있거나 형식이 다릅니다(값은 표시하지 않음)"

# ip= 를 비워 두면 DuckDNS 가 요청을 보낸 주소(이 서버의 공인 IP)로 설정한다
result="$(printf 'url = "https://www.duckdns.org/update?domains=%s&token=%s&ip="\n' "$sub" "$token" | curl -fsS --max-time 20 -K -)"
unset token
[[ "$result" == OK ]] || die "DuckDNS 갱신 실패(응답: $result). 도메인 이름과 토큰을 확인하세요"
ok "DuckDNS 갱신 완료: $domain → 이 서버의 공인 IP"
