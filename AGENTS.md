# AGENTS.md — 이 저장소에서 작업하는 AI 에이전트용 안내

CloudOps Monitor: 여러 서버의 CPU·RAM·디스크·네트워크를 한 화면에서 보고, 기준 초과와 연결 끊김을 장애 이력으로 남기는 모니터링 웹서비스.
고등학생 클라우드 엔지니어 지망생의 **포트폴리오 프로젝트**다. 목표는 Oracle Cloud Always Free(월 0원)에 HTTPS 로 공개하는 것.

자세한 설명은 `README.md`(아키텍처·API·보안·테스트 기록)에 있다. 이 파일은 **현재 상태, 지켜야 할 규칙, 다음 할 일**만 정리한다.

## 구성

| 폴더 | 내용 |
|---|---|
| `backend/` | Python FastAPI + SQLAlchemy 2 + SQLite. 설정은 환경변수 `CLOUDOPS_*` (`app/config.py`) |
| `frontend/` | React 19 + TypeScript + Vite + Tailwind CSS 4 + Recharts. nginx 로 서빙 |
| `agent/` | psutil 로 측정해 백엔드로 **push** 하는 에이전트 (대상 서버는 포트를 열지 않음) |
| `deploy/` | `Caddyfile`(HTTPS), `scripts/*.sh`(서버 준비·배포·상태·업데이트·백업·복원·DuckDNS) |
| `docs/` | `FREE_DEPLOY.md`(Oracle 무료 배포 순서), `BACKUP_RESTORE.md`, `DOCKER_VERIFY.md`(Docker 확인 명령·성공 기준), `PORTFOLIO.md` |
| 루트 | `docker-compose.yml`(HTTP, 127.0.0.1 전용), `docker-compose.https.yml`(Caddy 추가), `.env.example` |

핵심 설계(바꾸기 전에 README 1장을 읽을 것):
- Push 방식 → 백엔드가 사용자 입력 주소로 접속하지 않음(SSRF 차단).
- 서버 상태는 저장하지 않고 조회 시 "마지막 수신 시각 + 진행 중 장애"로 계산.
- 데모 데이터는 `is_demo=true` 로 분리, 화면·CSV 에 항상 `데모` 표시.
- 백그라운드 작업(연결 끊김 감시·데모·보존 정리)은 잠금 파일을 얻은 프로세스 하나만 실행.

## 테스트·빌드 명령

```bash
# 백엔드 (Python 3.12+)
cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest

# 프론트엔드 (Node 20.19+)
cd frontend && npm ci
npm run typecheck && npm test && npm run build

# 배포 스크립트 문법
for f in deploy/scripts/*.sh; do bash -n "$f"; done
```

변경 후에는 위 명령을 다시 돌리고, 결과를 숫자 그대로 보고한다.

## 마지막으로 확인한 결과 (2026-10-27, Linux 컨테이너, Python 3.13.17, Node 22.22.0)

| 항목 | 결과 |
|---|---|
| 백엔드 pytest | **155 passed** (기능 55 + 보안 73 + 운영 27). Starlette TestClient 의 httpx 사용 중단 예고 경고 1개 — 무해 |
| 프론트엔드 `tsc --noEmit` / vitest / `vite build` | 통과 / **17 passed** / 성공. 번들 500KB 초과 경고(Recharts) — 동작 영향 없음 |
| `deploy/scripts/*.sh` `bash -n` | 9개 모두 통과 |

## 아직 검증되지 않은 것 — 사실로 가정하지 말 것

- **Docker 는 한 번도 빌드·실행된 적이 없다.** `Dockerfile` 3개, compose 2개, `nginx.conf.template`, `Caddyfile` 은 정적 검토만 했다.
  README 9장의 "배포 스크립트 종단 간 43/43 통과"는 Docker 대신 **대역(stand-in)** 으로 스크립트를 돌린 결과이며, 2026-10-27 에는 다시 실행하지 못했다(그 컨테이너에 Docker 데몬이 없었음).
- 실제 Oracle 서버, `setup-server.sh`, DuckDNS + Let's Encrypt 발급, Caddy·nginx 의 실제 IP 전달, 재부팅 후 자동 복구.
- Linux/macOS 에서의 Agent, systemd 유닛, PostgreSQL 전환, 장시간·대규모 운영.

검증 방법과 성공 기준은 `docs/DOCKER_VERIFY.md` 에 있다.

## 규칙

- **비밀값을 커밋하지 않는다**: `.env`, DB(`*.db`), 백업, 인증서, SSH 키, DuckDNS 토큰. `.gitignore` 를 약하게 만들지 않는다. 출력·로그에도 비밀키·비밀번호·Agent 키를 찍지 않는다.
- 운영 스크립트는 실패 시 즉시 중단(`lib.sh` 의 `set -Eeuo pipefail`), **데이터 볼륨을 지우는 명령(`docker compose down -v` 등)을 넣지 않는다.**
- HTTP 포트는 `127.0.0.1` 에만 연다. 외부 공개는 Caddy(HTTPS)로만.
- Agent 는 본인 소유이거나 허가받은 서버에만 설치하도록 안내한다.
- 보안 동작(소유권 404, Origin 검사, 로그인 제한, 쿠키 속성 등)을 바꾸면 `backend/tests/test_security.py` 를 함께 갱신한다.
- 테스트를 지우거나 건너뛰게 만들어 통과시키지 않는다. 검증하지 못한 것은 "미검증"으로 적는다.
- 문서·주석은 한국어, 사용자(고등학생)가 따라 할 수 있는 수준으로 쓴다. 기존 README 의 "실행한 것 / 정적으로만 검토한 것" 구분을 유지한다.

## 다음 할 일 (우선순위 순)

1. Docker 가 되는 환경에서 `docs/DOCKER_VERIFY.md` 순서대로 이미지 빌드·실행 검증, 결과를 README 9장에 기록.
2. `docs/FREE_DEPLOY.md` 대로 Oracle Always Free 서버에 실제 배포(HTTPS) → Agent 연결 → 과정·스크린샷을 `docs/PORTFOLIO.md` 에 기록.
3. GitHub Actions 로 백엔드 pytest + 프론트엔드 typecheck/test/build 자동 실행.
4. (선택) 이메일/Slack 알림, 번들 분할(Recharts 동적 import), PostgreSQL 전환.
