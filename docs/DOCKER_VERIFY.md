# Docker 검증 안내

개발한 PC 에 Docker 가 없어 컨테이너는 **한 번도 빌드·실행하지 못했습니다.** 이 문서는 (1) 실행 없이 확인한 것, (2) 실행해야만 알 수 있는 것, (3) 나중에 직접 실행할 명령과 성공 기준을 구분해 적습니다.

> 서버 배포는 `deploy/scripts/` 의 스크립트(setup-server → deploy → status)로 진행합니다. 순서는 docs/FREE_DEPLOY.md.
> 이 문서는 스크립트와 별개로 **사람이 직접 확인하는 방법**과, 무엇이 실행 검증되었고 무엇이 아닌지를 정리합니다.

## 1. 실행 없이 확인한 것 (정적 검토)

| 항목 | 방법 | 결과 |
|---|---|---|
| compose 파일 YAML 문법 | PyYAML 로 두 파일 파싱 | 통과 |
| 서비스별 `build` 경로와 Dockerfile 존재 | 스크립트로 대조 | backend / frontend / agent 모두 존재 |
| Dockerfile 의 `COPY` 원본 파일 존재 | 스크립트로 대조 | 모두 존재 |
| compose 가 넘기는 환경변수 이름 = 백엔드 `Settings` 필드 | 스크립트로 대조 | 모르는 이름 없음 |
| compose 가 참조하는 변수가 `.env.example` 에 있는지 | 스크립트로 대조 | `CLOUDOPS_AGENT_KEY` 누락 → 추가함 |
| 줄바꿈(CRLF) | 바이트 검사 | Docker 관련 파일 전부 LF |
| `package-lock.json` 에 Linux(musl) 용 네이티브 패키지 포함 | 잠금 파일 검색 | rolldown · tailwind oxide · lightningcss 의 `linux-x64-musl`, `linux-arm64-musl` 포함 |
| 백엔드 포트 비공개 | compose 검토 | `expose` 만 있고 `ports` 없음 |
| 컨테이너 non-root 실행 | Dockerfile 검토 | backend(uid 10001), agent(uid 10002) |
| 데이터 영속성 | compose 검토 | `/app/data` 가 이름 있는 볼륨 `cloudops-data` |
| 비밀키 누락 시 동작 | compose 의 `${CLOUDOPS_SECRET_KEY:?…}` + 백엔드 기동 검사 | compose 가 먼저 오류를 내고, 우회해도 백엔드가 기동을 거부(백엔드 쪽은 실제 프로세스로 검증함) |
| 프록시 헤더 (1차) | nginx 설정 검토 | 클라이언트가 보낸 `X-Forwarded-For` 를 이어 붙여 전달 → 헤더 조작으로 로그인 실패 제한 우회 가능. nginx 가 본 주소로 덮어쓰도록 변경 |
| 프록시 헤더 (2차, 외부 점검) | 〃 | 1차 수정은 HTTPS 구성에서 실제 IP 를 Caddy IP 로 바꿈 → nginx `real_ip` 로 Caddy 고정 IP 한 개만 신뢰, 백엔드는 nginx 고정 IP 한 개만 신뢰하도록 변경 |
| 신뢰 주소 일관성 | 스크립트로 대조 | Caddy IP ∈ edge 서브넷, nginx IP ∈ app 서브넷, 두 서브넷 겹치지 않음, nginx 가 믿는 주소 = Caddy IP, 백엔드가 믿는 주소 = nginx IP, 와일드카드 신뢰 없음 |
| nginx 템플릿 | 스크립트로 검사 | 치환 대상 변수는 `CLOUDOPS_TRUSTED_PROXY` 하나, 중괄호 짝 맞음, 클라이언트 헤더를 이어 붙이는 `$proxy_add_x_forwarded_for` 없음 |
| ARM64·AMD64 호환 (2026-10-26) | `pip download --platform`, Docker Hub API, 잠금 파일 검사 | 의존성 휠·베이스 이미지 모두 두 아키텍처 제공. 프론트엔드 빌드 단계를 Alpine(musl)에서 `node:22-bookworm-slim`(glibc)으로 바꿈 — TypeScript 7 은 musl 전용 패키지가 없음 |
| nginx 이미지 (2026-10-26) | Docker Hub 갱신일 확인 | `nginx:1.27-alpine` 은 2025-04 이후 갱신이 없어 `nginx:1.30-alpine`(현재 stable)으로 교체 |
| 운영 설정 (2026-10-26) | compose 검사 | 프로젝트 이름 고정(`cloudops-monitor`), 모든 서비스 `restart: unless-stopped` + 로그 10MB×3, nginx HTTP 포트는 `127.0.0.1` 에만, frontend 헬스체크(nginx→FastAPI→DB), Caddy 는 frontend 가 healthy 일 때 시작 |
| 백엔드 쪽 IP 처리 | **실제 uvicorn 실행** | 신뢰 주소에서 온 헤더만 반영, 여러 주소면 가장 오른쪽 사용, 신뢰하지 않는 주소의 헤더는 무시, IP 별로 로그인 제한이 분리됨 |

## 2. 실행해야만 알 수 있는 것 (미검증)

- 이미지가 실제로 빌드되는지 (`pip install`, `npm ci`, `npm run build` 가 컨테이너 안에서 성공하는지)
  - 빌드 단계는 `node:22-bookworm-slim`(glibc)이고 잠금 파일에 ARM64·AMD64 용 네이티브 패키지가 있지만, 실제 ARM 서버에서 빌드가 끝까지 되는지는 돌려 봐야 압니다.
- nginx 설정이 문법 검사를 통과하고 `/api` 프록시가 동작하는지
- nginx 공식 이미지의 템플릿 치환이 `set_real_ip_from` 줄을 올바르게 만드는지
- 컨테이너에 고정 IP 가 실제로 붙는지, 서브넷이 서버의 다른 네트워크와 겹치지 않는지
- Caddy → nginx → FastAPI 를 거쳐 실제 사용자 IP 가 백엔드 로그에 찍히는지, 외부에서 조작한 헤더가 무시되는지
- 헬스체크가 통과해 frontend 가 backend 를 기다렸다가 뜨는지
- 볼륨 권한: non-root 계정이 `/app/data` 에 SQLite 파일을 쓸 수 있는지
- `docker compose down` → `up` 후 데이터가 남는지
- HTTPS 오버라이드: `!reset` 태그(Compose 2.24 이상 필요), Caddy 인증서 발급, `Secure` 쿠키
- Agent 컨테이너에서의 측정값
- ARM(예: Apple Silicon, AWS Graviton)에서의 빌드

## 3. 나중에 실행할 명령과 성공 기준

모든 명령은 `cloudops-monitor` 폴더에서 실행합니다.

### 3-1. 준비

```bash
docker --version
```

```bash
docker compose version
```

성공 기준: 버전이 출력되고 Compose 가 2.24 이상.

```bash
cp .env.example .env
```

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

출력된 값을 `.env` 의 `CLOUDOPS_SECRET_KEY=` 뒤에 붙여 넣습니다.

### 3-2. 설정 확인 (컨테이너를 띄우지 않음)

```bash
docker compose config --quiet
```

성공 기준: 아무 출력 없이 종료코드 0. `.env` 에 키가 없으면 "CLOUDOPS_SECRET_KEY 를 설정하세요" 오류가 나와야 정상입니다.

### 3-3. 빌드와 실행

```bash
docker compose up -d --build
```

```bash
docker compose ps
```

성공 기준: `backend` 가 `healthy`, `frontend` 가 `running`, 포트는 frontend 의 `8080->80` 만 보임.

### 3-4. 동작 확인

```bash
curl -s http://localhost:8080/api/v1/health
```

성공 기준: `{"status":"ok"}`

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/v1/servers
```

성공 기준: `401` (로그인 없이는 조회 불가)

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8080/api/docs
```

성공 기준: `404` (운영 모드에서는 API 문서를 공개하지 않음). `200` 이면 운영 모드가 적용되지 않은 것입니다.

```bash
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8000/api/v1/health
```

성공 기준: 연결 실패 (백엔드 포트는 호스트에 열려 있지 않아야 함)

```bash
curl -sI http://localhost:8080/ | grep -i -E "content-security-policy|x-frame-options"
```

성공 기준: 두 헤더가 모두 출력됨.

```bash
docker compose exec backend id -u
```

성공 기준: `10001` (root 인 0 이 아님)

브라우저에서 `http://localhost:8080` → 회원가입 → "데모 서버 4대 추가" → 그래프가 3초마다 움직이는지 확인합니다.

### 3-5. 데이터 유지

```bash
docker compose down
```

```bash
docker compose up -d
```

성공 기준: 다시 로그인했을 때 서버·장애 이력이 그대로 있고, **로그인 세션도 유지**됩니다(`.env` 의 키가 고정이므로).

### 3-6. 비밀키 누락

```bash
CLOUDOPS_SECRET_KEY= docker compose config --quiet
```

성공 기준: 오류로 종료 (빈 키로는 시작할 수 없음). 확인 후 `.env` 의 값은 그대로 두세요.

### 3-7. 로그에 비밀정보가 없는지

```bash
docker compose logs backend | grep -c -E "cops_|argon2"
```

성공 기준: `0`

### 3-8. 실제 사용자 IP 와 헤더 조작 (HTTP 구성)

```bash
docker compose exec frontend grep set_real_ip_from /etc/nginx/conf.d/default.conf
```

성공 기준: `set_real_ip_from 127.0.0.1/32;` (HTTP 구성에서는 신뢰하는 프록시 없음)

```bash
curl -s -o /dev/null -X POST -H "Content-Type: application/json" -H "X-Forwarded-For: 1.2.3.4" -d "{\"email\":\"nobody@example.com\",\"password\":\"wrong-password\"}" http://localhost:8080/api/v1/auth/login
```

```bash
docker compose logs backend | grep "auth/login" | tail -1
```

성공 기준: 줄 앞의 주소가 `1.2.3.4` 가 **아니어야** 합니다(호스트 또는 Docker 게이트웨이 주소가 보이면 정상).

### 3-9. 실제 사용자 IP (HTTPS 구성)

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml exec frontend grep set_real_ip_from /etc/nginx/conf.d/default.conf
```

성공 기준: `set_real_ip_from 172.30.0.2/32;`

다른 PC 나 휴대폰(LTE)에서 `https://도메인` 에 접속해 틀린 비밀번호로 로그인한 뒤:

```bash
docker compose -f docker-compose.yml -f docker-compose.https.yml logs backend | grep "auth/login" | tail -1
```

성공 기준: 그 기기의 공인 IP 가 보임. `172.30.0.2`(Caddy) 나 `172.31.0.10`(nginx) 이 보이면 신뢰 설정이 맞지 않는 것입니다. 같은 기기에서 `-H "X-Forwarded-For: 1.2.3.4"` 를 붙인 curl 로 요청해도 `1.2.3.4` 가 아니라 실제 IP 가 보여야 합니다.

### 3-10. Agent 컨테이너 (선택)

웹에서 서버를 등록해 받은 키로:

```bash
CLOUDOPS_AGENT_KEY=cops_여기에_키 docker compose --profile agent up -d --build agent
```

```bash
docker compose logs agent
```

성공 기준: "시작: host=…" 뒤에 "전송 실패"가 없고, 웹에서 해당 서버가 "데이터 대기"에서 "정상"으로 바뀜.

### 3-11. 정리

```bash
docker compose --profile agent down
```

데이터까지 지우려면 `-v` 를 붙입니다(되돌릴 수 없음).

## 4. 실패했을 때 볼 곳

| 증상 | 확인 |
|---|---|
| frontend 빌드 중 `Killed` 또는 멈춤 | 메모리 부족. `free -h` 로 스왑 확인, `sudo deploy/scripts/setup-server.sh` 가 1GB 서버에 2GB 스왑을 만든다 |
| backend 가 `unhealthy` | `docker compose logs backend` — 비밀키 오류 또는 `/app/data` 쓰기 권한 |
| 화면은 뜨는데 로그인 불가 | `docker compose logs frontend` 의 `/api` 프록시 오류 |
| HTTPS 에서만 로그인 불가 | `CLOUDOPS_COOKIE_SECURE` 와 실제 접속 프로토콜이 맞는지 |
| `Pool overlaps with other one on this address space` | `.env` 에서 `CLOUDOPS_APP_SUBNET`/`CLOUDOPS_NGINX_IP` 또는 `CLOUDOPS_EDGE_SUBNET`/`CLOUDOPS_CADDY_IP` 를 겹치지 않는 대역으로 짝 맞춰 변경 |
| 백엔드 로그에 모든 요청이 `172.31.0.10` 으로 찍힘 | 백엔드의 `FORWARDED_ALLOW_IPS` 와 nginx 컨테이너 실제 IP 가 같은지 (`docker compose exec frontend hostname -i`) |
| HTTPS 에서 모든 요청이 `172.30.0.2` 로 찍힘 | nginx 의 `set_real_ip_from` 이 Caddy 실제 IP 와 같은지 |
