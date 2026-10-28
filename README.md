# CloudOps Monitor

여러 서버의 CPU·RAM·디스크·네트워크 상태를 한 화면에서 실시간으로 확인하고, 기준 초과와 연결 끊김을 장애 이력으로 남기는 서버 모니터링 웹서비스입니다.

- **Frontend** React 19 + TypeScript + Vite + Tailwind CSS 4 + Recharts
- **Backend** Python FastAPI + SQLAlchemy 2 + SQLite
- **Agent** Python + psutil (모니터링 대상 서버에서 실행)
- **Deploy** Docker Compose (+ Caddy 로 HTTPS)

> 반드시 **본인 소유이거나 모니터링 허가를 받은 서버**에만 Agent 를 설치하세요.

---

## 1. 아키텍처

```
 모니터링 대상 서버 (N대)                    모니터링 서버 (Docker Compose)
┌──────────────────────┐              ┌───────────────────────────────────────────────┐
│ agent.py (psutil)    │  HTTPS POST  │  nginx (frontend 컨테이너)                      │
│  - 5초마다 측정        │ ───────────▶ │   ├─ /        React 정적 파일                   │
│  - Bearer Agent 키    │  /api/v1/    │   └─ /api/*   ──▶ FastAPI (backend 컨테이너)     │
│  - 포트를 열지 않음     │   ingest     │                    ├─ 인증 / 서버 / 장애 / 대시보드 │
└──────────────────────┘              │                    ├─ 장애 감지 (수집 시점에 평가)  │
                                      │                    ├─ 백그라운드: 연결 끊김 감시,   │
 브라우저 ── 쿠키 세션 ── 3초 폴링 ───────▶ │                    │   데모 시뮬레이터, 보존 기간 정리│
                                      │                    └─ SQLite (볼륨에 저장)         │
                                      └───────────────────────────────────────────────┘
```

핵심 설계 결정 세 가지:

1. **Push 방식** — Agent 가 백엔드로 보냅니다. 백엔드는 등록된 서버 주소로 접속하지 않습니다. 그래서 사용자가 입력한 주소를 이용한 SSRF 가 구조적으로 불가능하고, 대상 서버는 방화벽 인바운드 포트를 열 필요가 없습니다.
2. **상태는 저장하지 않고 계산** — `정상/경고/장애/연결 끊김/데이터 대기` 는 조회할 때마다 "마지막 수신 시각"과 "진행 중 장애"로 계산합니다. Agent 가 조용히 죽어도 마지막에 저장된 "정상"이 계속 보이는 일이 없습니다.
3. **가상 데이터와 실제 데이터의 분리** — 가상 서버는 `is_demo=true` 로 저장되어 화면·CSV 에 항상 `데모` 로 표시되고, Agent 키가 없어 실제 수집 API 로는 쓸 수 없습니다.

## 2. 폴더 구조

```
cloudops-monitor/
├─ backend/
│  ├─ app/
│  │  ├─ main.py            앱 생성, 보안 헤더, Origin 검사, 라우터 등록, 백그라운드 작업 시작
│  │  ├─ maintenance.py     SQLite 백업·검증·복원 도구 (배포 스크립트가 호출)
│  │  ├─ config.py          환경변수 설정 (CLOUDOPS_*)
│  │  ├─ database.py        엔진/세션, UTC 시간 타입, SQLite PRAGMA
│  │  ├─ models.py          User, Server, Metric, Incident
│  │  ├─ schemas.py         요청/응답 검증 (Pydantic)
│  │  ├─ security.py        Argon2 해싱, JWT, Agent 키, 로그인 제한
│  │  ├─ deps.py            인증·소유권 확인 의존성
│  │  ├─ routers/           auth, servers, incidents, misc(대시보드·수집·데모)
│  │  └─ services/          status, alerts, metrics, demo, background, locking(단일 실행 잠금)
│  ├─ tests/                pytest 155개 (기능 55 + 보안 점검 73 + 운영 27)
│  └─ Dockerfile
├─ agent/
│  ├─ agent.py              psutil 측정 → 백엔드 전송
│  ├─ cloudops-agent.service  systemd 유닛 예시
│  └─ Dockerfile
├─ frontend/
│  ├─ src/
│  │  ├─ api/               fetch 클라이언트, 타입
│  │  ├─ components/        Layout, MetricChart, ServerCard, 모달, 배지 …
│  │  ├─ context/           로그인 상태, 테마
│  │  ├─ hooks/usePolling.ts
│  │  ├─ lib/               단위 변환, 그래프 공백 처리, 요청이 겹치지 않는 폴링(poller.ts) (+ vitest)
│  │  └─ pages/             Login, Dashboard, Servers, ServerDetail, Incidents
│  ├─ nginx.conf.template  nginx 설정 (시작할 때 신뢰 프록시 주소만 치환)
│  └─ Dockerfile
├─ deploy/
│  ├─ Caddyfile            HTTPS 리버스 프록시 (Let's Encrypt 자동 발급)
│  └─ scripts/             서버 운영 스크립트
│     ├─ setup-server.sh   Ubuntu 준비: Docker 설치·자동 시작, 80/443 허용, 스왑, 보안 업데이트
│     ├─ check.sh          환경·필수 설정 검사 (비밀값은 출력하지 않음)
│     ├─ deploy.sh         최초 배포 (.env·비밀키 생성 → 검사 → 빌드 → 시작 → 상태 확인)
│     ├─ status.sh         상태 확인 (컨테이너, 내부/HTTPS, 인증서, 디스크, 백업)
│     ├─ update.sh         업데이트 (검사 → 백업 → 빌드 → 재시작 → 상태 확인)
│     ├─ backup.sh         SQLite 일관성 백업 (+ 압축·체크섬·보관 개수)
│     ├─ restore.sh        백업 복원 (검증 → 안전 백업 → 정지 → 교체 → 시작)
│     ├─ duckdns-update.sh 무료 도메인(DuckDNS) IP 갱신 (선택)
│     └─ lib.sh            공통 함수
├─ docker-compose.yml
├─ docker-compose.https.yml
├─ .env.example
└─ docs/                    FREE_DEPLOY.md, BACKUP_RESTORE.md, DOCKER_VERIFY.md, PORTFOLIO.md, pytest-output.txt
```

## 3. 데이터베이스

| 테이블 | 주요 컬럼 | 설명 |
|---|---|---|
| `users` | email(unique), password_hash | Argon2id 해시만 저장 |
| `servers` | owner_id→users, name, host, os_name, is_demo, agent_key_hash(unique), `*_warn`/`*_crit` 6개, last_seen_at | 서버 설정과 알림 기준. Agent 키는 SHA-256 해시만 저장 |
| `metrics` | server_id→servers, ts, cpu/mem/disk %, 사용량, 네트워크 속도·누적, uptime | 인덱스 `(server_id, ts)`. ts 는 백엔드 수신 시각 |
| `incidents` | server_id→servers, metric, severity, started_at, resolved_at, threshold, peak_value, clear_streak | 부분 유니크 인덱스 `(server_id, metric) WHERE resolved_at IS NULL` |

- 서버를 삭제하면 `ON DELETE CASCADE` 로 측정값과 장애 이력이 함께 삭제됩니다.
- `incidents` 의 부분 유니크 인덱스가 "같은 서버·같은 항목의 진행 중 장애는 1건"을 DB 수준에서 보장합니다(중복 알림 방지).
- 테이블은 시작할 때 `create_all` 로 만듭니다. 스키마를 바꿔 가며 운영하려면 Alembic 마이그레이션을 추가해야 합니다(미포함).

## 4. 실행 방법

### A. 무료 클라우드 서버에 배포 (HTTPS)

Oracle Cloud Always Free + DuckDNS 무료 도메인으로 월 0원 배포하는 전체 순서(계정 만들기, 서버 생성, 방화벽, HTTPS, Agent 연결)는
**[docs/FREE_DEPLOY.md](docs/FREE_DEPLOY.md)** 에 있습니다. 서버에서 실행하는 명령은 다음 세 개입니다.

```bash
sudo deploy/scripts/setup-server.sh
```

```bash
deploy/scripts/deploy.sh
```

```bash
deploy/scripts/status.sh
```

백업·복원·PC 로 내려받기: **[docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md)**

### A-2. 내 PC 에서 Docker 로 실행 (HTTP, localhost 전용)

```bash
cp .env.example .env
```

`.env` 를 열어 `CLOUDOPS_SECRET_KEY` 에 32자 이상 난수를 넣습니다. 생성 예:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

```bash
docker compose up -d --build
```

브라우저에서 `http://localhost:8080` → 회원가입 → **데모 서버 4대 추가**. 이 구성은 `127.0.0.1` 에만 열리므로 다른 기기에서는 접속되지 않습니다(인터넷 공개는 A 의 HTTPS 구성으로).

### B. 로컬 실행 (Docker 없이)

프로젝트는 **폴더 위치에 의존하지 않습니다.** 소스 안에 절대 경로가 없으므로 폴더를 통째로 옮기거나 ZIP 을 다른 곳에 풀어도 아래 순서 그대로 실행됩니다. 필요한 것은 Python 3.12 이상과 Node 20.19 이상입니다.

아래 명령은 모두 `cloudops-monitor` 폴더에서 시작합니다. 터미널을 두 개 엽니다.

**터미널 1 — 백엔드** (Windows PowerShell)

```bash
cd backend
```

```bash
py -m venv .venv
```

```bash
.venv\Scripts\python -m pip install -r requirements-dev.txt
```

```bash
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

macOS / Linux 에서는 `py` 대신 `python3`, `.venv\Scripts\python` 대신 `.venv/bin/python` 을 씁니다.

**터미널 2 — 프론트엔드**

```bash
cd frontend
```

```bash
npm ci
```

```bash
npm run dev
```

브라우저에서 `http://localhost:5173` 으로 접속합니다. Vite 가 `/api` 요청을 8000 포트로 넘겨 줍니다. API 문서는 `http://localhost:8000/api/docs` (개발 환경에서만 열림).

성공 확인: `http://localhost:8000/api/v1/health` 가 `{"status":"ok"}` 를 돌려주고, 5173 화면에서 회원가입 후 "데모 서버 4대 추가"가 동작하면 됩니다.

알아 둘 점:

- **데이터베이스 위치는 백엔드를 실행한 폴더 기준**입니다(`./data/cloudops.db`). 위 순서대로 `backend` 폴더에서 실행하면 `backend/data/cloudops.db` 에 만들어집니다. 다른 폴더에서 실행하면 그 폴더에 새 DB 가 생겨 "데이터가 사라진 것처럼" 보이니, 항상 같은 폴더에서 실행하거나 `CLOUDOPS_DATABASE_URL` 로 경로를 고정하세요.
- **비밀키**: `CLOUDOPS_SECRET_KEY` 를 지정하지 않으면 실행할 때마다 임시 키를 만들므로 백엔드를 재시작하면 로그인이 풀립니다(데이터는 유지). `backend/.env` 파일에 `CLOUDOPS_SECRET_KEY=<32자 이상 난수>` 한 줄을 넣으면 유지됩니다. `.env` 도 실행한 폴더에서 읽습니다.
- **Windows 경로 길이**: 폴더 경로가 매우 길면 `py -m venv .venv` 가 `WinError 206` 으로 실패합니다. 이때는 가상환경만 짧은 경로에 만들면 됩니다. 예: `py -m venv $HOME\.venvs\cloudops` 로 만든 뒤 `backend` 폴더에서 `& $HOME\.venvs\cloudops\Scripts\python -m uvicorn app.main:app --port 8000`. 가상환경에는 라이브러리만 들어 있고 프로젝트 경로를 기억하지 않으므로, 프로젝트를 옮겨도 다시 만들 필요가 없습니다.
- **가상환경과 `node_modules` 는 배포 ZIP 에 없습니다.** 위의 `pip install` 과 `npm ci` 가 `requirements*.txt` 와 `package-lock.json` 으로 다시 만들어 줍니다.

## 5. 실제 서버 연결 (Agent)

1. 웹에서 **서버 등록** → Agent 인증키(`cops_…`)가 **한 번만** 표시됩니다.
2. 대상 서버에 `agent/agent.py` 를 복사하고 실행합니다.

```bash
pip install psutil
export CLOUDOPS_URL="https://monitor.example.com"
export CLOUDOPS_AGENT_KEY="cops_xxxxxxxx"
python agent.py
```

| 옵션 | 설명 |
|---|---|
| `--print` | 전송 없이 측정값만 출력 (설치 확인용) |
| `--once` | 한 번 전송하고 종료 (연결 확인용) |
| `CLOUDOPS_INTERVAL` | 전송 주기(초), 기본 5, 최소 2 |
| `CLOUDOPS_DISK_PATH` | 측정할 디스크 경로, 기본 `/` (Windows 는 시스템 드라이브) |
| `CLOUDOPS_ALLOW_INSECURE=1` | localhost 가 아닌 주소에 http 허용(신뢰하는 사설망에서만) |

상시 실행은 `agent/cloudops-agent.service` (systemd) 주석을 따라 설정합니다. 전송이 실패하면 지수 백오프(최대 60초)로 재시도하고, 인증키가 거부되면 즉시 종료합니다.

상태 표시 규칙:

| 상태 | 조건 |
|---|---|
| 데이터 대기 | 등록 후 한 번도 데이터를 받지 못함 |
| 정상 / 경고 / 장애 | 최근 30초 안에 수신 + 진행 중 장애의 최고 심각도 |
| 연결 끊김 | 30초(`CLOUDOPS_OFFLINE_AFTER_SECONDS`) 넘게 수신 없음. 이때 화면의 수치는 "마지막으로 받은 값"으로 흐리게 표시되고 평균 계산에서 제외 |

장애 감지 규칙: 기준 이상이면 장애 1건 생성 → 이어지는 동안은 최고값·심각도만 갱신 → 기준 아래 샘플이 **연속 3회** 나와야 해결 처리(값이 기준 근처에서 오르내릴 때 알림이 쏟아지는 것을 방지).

## 6. API 요약 (`/api/v1`)

| 메서드 | 경로 | 인증 | 설명 |
|---|---|---|---|
| POST | `/auth/register` `/auth/login` `/auth/logout` | – | 세션 쿠키 발급/삭제 |
| GET | `/auth/me` | 쿠키 | 현재 사용자 |
| GET·POST | `/servers` | 쿠키 | 목록 / 등록(Agent 키 1회 반환) |
| GET·PUT·DELETE | `/servers/{id}` | 쿠키+소유자 | 조회 / 수정 / 삭제 |
| POST | `/servers/{id}/rotate-key` | 쿠키+소유자 | Agent 키 재발급(기존 키 즉시 무효) |
| GET | `/servers/{id}/metrics?range=1m\|5m\|1h\|24h` | 쿠키+소유자 | 시계열(1h 는 30초, 24h 는 5분 평균) |
| GET | `/servers/{id}/metrics/export?range=` | 쿠키+소유자 | CSV |
| GET | `/incidents?state=&server_id=&limit=` `/incidents/export` | 쿠키 | 장애 이력 / CSV |
| GET | `/dashboard/summary` `/dashboard/timeseries?range=` | 쿠키 | 요약 / 전체 평균 추이 |
| POST | `/ingest` | **Agent 키** | 측정값 수집 |
| POST·DELETE | `/demo/seed` `/demo` | 쿠키 | 가상 서버 생성 / 제거 |
| GET | `/health` `/config` | – | 헬스체크 / 공개 설정 |

## 7. 보안

| 요구사항 | 구현 |
|---|---|
| 인증된 사용자만 조회 | 모든 데이터 API 가 `get_current_user` 의존성을 거침. 테스트 `test_protected_endpoints_require_login` |
| 비밀번호 해싱 | Argon2id (`argon2-cffi`). 로그인 실패 시 계정 존재 여부를 구분하지 않고, 없는 계정도 더미 해시로 같은 시간 소요 |
| 무차별 대입 방지 | IP+이메일 기준 5분에 5회 실패 시 429 |
| 세션 | JWT 를 `HttpOnly; SameSite=Lax` 쿠키로 전달(JS 가 토큰에 접근 불가). HTTPS 에서는 `Secure` 추가 |
| 입력값 검증 | Pydantic 스키마. 호스트는 IP/호스트명 형식만 허용, 수집 페이로드는 엄격 타입·범위 검사 + 알 수 없는 필드 거부. 검증 오류 응답에 입력값을 되돌려 주지 않음 |
| 접근 권한 | 서버·측정값·장애 모두 `owner_id` 로 필터링. 남의 리소스는 404. 테스트 `test_users_cannot_see_or_modify_each_others_servers` |
| Agent 키 | 256bit 난수, DB 에는 SHA-256 해시만 저장, 발급 시 1회만 표시, 재발급 시 기존 키 즉시 무효 |
| 비밀정보 | 전부 환경변수(`.env`). production 에서 `SECRET_KEY` 가 32자 미만이면 기동 거부 |
| SSRF | 백엔드가 사용자 입력 주소로 요청을 보내는 코드가 없음(push 구조) |
| 명령어 삽입 / 임의 명령 실행 | 백엔드·Agent 어디에도 셸 실행(`subprocess`, `os.system`) 없음. Agent 는 백엔드 응답을 해석하지 않음 |
| SQL 삽입 | SQLAlchemy 바인딩 파라미터만 사용 |
| XSS | React 기본 이스케이프 + nginx CSP(`script-src 'self'`) |
| CSV 수식 삽입 | `=`,`+`,`-`,`@` 로 시작하는 셀 앞에 `'` 추가 |
| 실제 사용자 IP | 신뢰하는 프록시를 주소 하나로 고정: nginx 는 Caddy 의 IP 만, 백엔드는 nginx 의 IP 만 신뢰. 외부에서 조작한 `X-Forwarded-For` 로 로그인 실패 제한을 피할 수 없음 |
| 로그아웃 | 서버가 세션 쿠키를 지운 것이 확인될 때만 로그아웃 화면으로 이동. 실패하면 로그인 상태임을 알리고 재시도 제공 |
| 기타 | 보안 헤더(nosniff, frame DENY), production 에서 API 문서 비공개, 컨테이너 non-root 실행, 백엔드 포트 비공개 |

**알려진 한계** (숨기지 않고 적어 둡니다)

- 로그인 제한기와 백그라운드 작업이 프로세스 메모리에 있어 백엔드 워커는 1개로 고정해야 합니다. 여러 대로 늘리려면 Redis 등 외부 저장소가 필요합니다.
- 로그아웃은 쿠키를 지우는 방식이라, 이미 탈취된 토큰은 만료(기본 12시간)까지 유효합니다. 서버 측 세션 폐기 목록은 없습니다.
- 이메일 인증, 비밀번호 재설정, 2단계 인증, 관리자/일반 사용자 역할 구분은 없습니다.
- 알림은 화면과 장애 이력에만 남습니다. 이메일·Slack 발송은 없습니다.

## 8. HTTPS

도메인이 있고 80/443 포트가 열려 있으면 Caddy 가 인증서를 자동 발급합니다.

```bash
# .env 에 CLOUDOPS_DOMAIN=monitor.example.com 추가 후
docker compose -f docker-compose.yml -f docker-compose.https.yml up -d --build
```

이 구성은 세션 쿠키에 `Secure` 를 켜고, 8080 직접 공개를 끄고, HSTS 헤더를 추가합니다.

실제 사용자 IP 가 백엔드까지 전달되는 방식:

```
사용자(203.0.113.7) ─▶ Caddy 172.30.0.2 ─▶ nginx 172.31.0.10 ─▶ FastAPI
                      XFF: 203.0.113.7     XFF: 203.0.113.7     client = 203.0.113.7
```

| 단계 | 누구의 헤더를 믿나 | 설정 위치 |
|---|---|---|
| Caddy | 인터넷에서 온 `X-Forwarded-For` 는 믿지 않고(Caddy 기본 동작) 직접 본 주소를 기록 | `deploy/Caddyfile` |
| nginx | `CLOUDOPS_TRUSTED_PROXY` (HTTPS 구성: Caddy IP `/32`, HTTP 구성: 없음=`127.0.0.1/32`) | `frontend/nginx.conf.template`, `docker-compose.https.yml` |
| FastAPI | `FORWARDED_ALLOW_IPS` = nginx IP 한 개 | `docker-compose.yml` |

- 주소를 고정하려고 두 네트워크의 서브넷을 지정했습니다(`172.31.0.0/24`, `172.30.0.0/24`). 서버의 다른 네트워크와 겹쳐 `Pool overlaps` 오류가 나면 `.env` 의 `CLOUDOPS_APP_SUBNET`·`CLOUDOPS_NGINX_IP`, `CLOUDOPS_EDGE_SUBNET`·`CLOUDOPS_CADDY_IP` 를 짝으로 바꿉니다.
- ALB 등 다른 프록시를 앞에 둘 때는 그 프록시의 주소 범위를 `CLOUDOPS_TRUSTED_PROXY` 에 넣습니다. 범위를 넓게 잡을수록 그 범위 안의 누구나 헤더를 조작할 수 있으므로 가능한 한 좁게 지정하세요. AWS 등에서는 Caddy 대신 로드밸런서(ALB)+ACM 인증서를 앞에 두고 `CLOUDOPS_COOKIE_SECURE=true` 만 설정해도 됩니다.

## 9. 테스트

```bash
cd backend && python -m pytest
```

```bash
cd frontend && npm test && npm run build
```

### 실행 결과 (2026-10-13, Windows 11 · Python 3.14.3 · Node 24.21)

| 항목 | 결과 |
|---|---|
| 백엔드 pytest | **128 passed** (2026-10-25 기준. 현재는 155개 — 아래 "무료 클라우드 배포 준비 검증") |
| 프론트엔드 vitest | **17 passed** |
| 프론트엔드 `tsc --noEmit` + `vite build` | 성공 |
| 수동: 브라우저에서 회원가입 → 데모 서버 4대 생성 → 대시보드·그래프 표시 | 확인 |
| 수동: 실제 서버 등록 → 이 PC 에서 `agent.py` 실행 → 실측값 표시, 경고 발생 | 확인 |
| 수동: Agent 중지 → 30초 뒤 `연결 끊김` 표시 + 장애 기록, 그래프 끊김 | 확인 |
| 수동: 백엔드 재시작 → 계정·서버·알림 기준·장애 이력 유지 | 확인 |
| 수동: CSV 내보내기(측정값, 장애), 다크/라이트, 모바일(375px) | 확인 |

### 보안 점검 (`tests/test_security.py` 73개 + 실제 프로세스 확인)

| 점검 | 방법 | 결과 |
|---|---|---|
| 사용자 B 가 A 의 서버 ID 를 직접 넣어 조회·수정·삭제·키 재발급·측정 기록·CSV 요청 | 자동 테스트 + 운영 모드로 띄운 실제 서버에 HTTP 요청 | 전부 404, A 의 데이터 변화 없음 |
| B 가 A 서버의 장애 이력을 목록·서버 ID 지정·CSV 로 요청 | 〃 | 빈 결과(CSV 는 헤더만) |
| 로그인하지 않은 요청 16종 | 〃 | 전부 401 |
| Agent 키로 사용자 API 접근 | 자동 테스트 | 401 |
| A 서버 키로 다른 서버에 기록 시도(본문에 `server_id` 등 삽입, 쿼리 파라미터) | 자동 테스트 + 실제 서버 | 본문 삽입은 422, 쿼리는 무시. 다른 서버에 기록되지 않음 |
| 삭제된 서버의 키, 재발급 전의 키, DB 의 키 해시를 키로 사용 | 자동 테스트 | 401 |
| 잘못된 키 11종 | 자동 테스트 | 401, 기록 없음 |
| 비정상 측정값 26종 + NaN/Infinity + 필드 누락 + 깨진 본문 | 자동 테스트 | 422, 기록·장애·수신 시각 모두 변화 없음 |
| 운영 모드에서 비밀키 없음 / 32자 미만 | 자동 테스트 + 실제 `uvicorn` 실행 | 기동 거부(종료코드 1, 오류에 변수명 표시) |
| 개발 모드에서 비밀키 없음 | 자동 테스트 | 매번 새 난수 키 사용 + 경고. 키 값은 로그에 없음 |
| 비밀키·비밀번호·Agent 키·세션 토큰·해시가 로그에 남는지 | 자동 테스트(로그 캡처) + 실제 서버 로그 검색 | 없음 |
| 조회 API 응답과 프론트엔드 빌드 결과물에 비밀정보가 있는지 | 자동 테스트 + `dist/` 검색 | 없음. 평문 Agent 키는 발급 응답 1회뿐 |
| 프론트엔드 저장소 사용 | 소스 검색 | `localStorage` 에는 테마 설정만 저장. 토큰은 JS 가 읽을 수 없는 쿠키 |

점검 중 발견해 고친 문제:

1. **422 오류 응답이 보낸 값을 그대로 되돌려 줌** — 가입 시 비밀번호가 규칙에 맞지 않으면 그 비밀번호가 응답 본문에 포함됐습니다(요청한 본인에게만 가지만 프록시 로그에 남을 수 있음). 오류 위치와 메시지만 돌려주도록 변경.
2. **수집 API 가 숫자 모양 문자열을 받아 줌** — `"cpu_percent": "50"`, `true` 같은 값이 숫자로 바뀌어 저장됐습니다. 엄격 모드로 변경하고 NaN/Infinity 를 명시적으로 거부.
3. **사용량이 전체 용량보다 큰 값을 받아 줌** — `mem_used > mem_total`, `disk_used > disk_total` 을 거부하도록 검증 추가.
4. **nginx 가 클라이언트의 `X-Forwarded-For` 를 그대로 이어 붙여 전달** — 헤더를 조작해 로그인 실패 제한을 피할 수 있었습니다. nginx 가 본 주소로 덮어쓰도록 변경. → 이 방식은 HTTPS 구성에서 실제 사용자 IP 를 Caddy IP 로 바꿔 버리는 문제가 있어, 아래 "외부 점검 후 수정" 3번에서 다시 고쳤습니다.
5. `.env.example` 에 `CLOUDOPS_AGENT_KEY` 설명 누락 → 추가.

### 외부 점검 후 수정 (2026-10-25)

| # | 문제 | 수정 | 검증 |
|---|---|---|---|
| 1 | 3초 폴링에서 응답이 매번 4초 걸리면, 요청이 계속 겹치고 "가장 최근 요청의 응답만 받는" 규칙 때문에 모든 응답이 버려져 화면이 멈춤 | 요청을 한 번에 하나만 보내고, 응답을 받은 뒤 다음 요청을 예약(`frontend/src/lib/poller.ts`). 화면 이동·조건 변경 시 이전 응답을 버리는 동작은 유지. 응답이 오지 않는 요청이 폴링 전체를 멈추지 않도록 요청 제한 시간 15초 추가 | 단위 테스트 9개(수정 전 방식이 30초 동안 한 번도 갱신하지 못하는 것도 재현) + 실제 화면에서 모든 응답을 4초 늦춰 32초 관찰: 약 7초마다 값 갱신, 동시 요청 최대 1개 |
| 2 | 로그아웃 API 가 실패해도 오류를 무시하고 로그인 화면으로 이동. 세션 쿠키는 서버만 지울 수 있으므로 실제로는 로그인 상태가 남음 | 서버 로그아웃이 성공했을 때만 로그아웃 처리. 실패하면 "아직 로그인된 상태"라는 안내와 **다시 시도** / **로그인 유지** 버튼을 화면 상단에 고정 표시 | 실제 화면에서 백엔드를 끈 채 로그아웃 → 안내 표시, 세션 유효(200) 확인 → 백엔드 재시작 후 "다시 시도" → 로그인 화면, 세션 무효(401) |
| 3 | HTTPS 구성(Caddy → nginx → FastAPI)에서 nginx 가 `X-Forwarded-For` 를 자신이 본 주소로 덮어써, 백엔드가 모든 사용자를 Caddy IP 로 인식 | nginx 는 **Caddy 의 고정 IP 한 개**에서 온 헤더만 읽어 실제 IP 를 복원하고(`real_ip`), 그 외 연결이 보낸 헤더는 무시. 백엔드(uvicorn)는 와일드카드(`*`) 대신 **nginx 의 고정 IP 한 개**에서 온 헤더만 신뢰 | uvicorn 쪽은 실제 프로세스로 확인(신뢰 주소에서 온 헤더만 반영, 여러 주소가 있으면 가장 오른쪽 사용, IP 별 로그인 제한 분리). nginx·Caddy·compose 네트워크는 Docker 가 없어 **정적 검토만** |
| 4 | (점검 중 추가 발견) 로그아웃 실패 안내가 페이지 맨 위에만 있어, 스크롤을 내린 상태에서 사이드바의 로그아웃을 누르면 안내가 보이지 않음 | 안내를 화면 상단에 고정 | 스크롤한 상태에서 화면으로 확인 |

### 무료 클라우드 배포 준비 검증 (2026-10-26)

Docker 와 Linux 서버가 없는 Windows PC 에서 진행했습니다. **실행한 것**과 **정적으로만 검토한 것**을 구분합니다.

**자동 테스트 (실행)**

| 항목 | 결과 |
|---|---|
| 백엔드 pytest | **155 passed** (운영 기능 27개 추가: 단일 실행 잠금, 강제 종료된 프로세스의 잠금 해제, 상태 확인 503, Origin 검사, 보존 기간, 백업 일관성·검증·복원·실행 중 복원 거부) |
| 프론트엔드 vitest · `tsc --noEmit` · `vite build` | 17 passed · 통과 · 성공 |
| 브라우저: 느린 응답 폴링 | 모든 응답 4초 지연 → 약 7초마다 갱신, 동시 요청 최대 1개 |
| 브라우저: 로그아웃 실패 → 재시도 | 백엔드 정지 상태에서 실패 안내 표시(페이지 아래로 스크롤한 상태에서도 화면 안), 세션 유지(200) → 재시작 후 다시 시도 → 로그인 화면, 세션 종료(401) |

**배포 스크립트 종단 간 검증 (실행, 43/43 통과)**

`deploy/scripts/*.sh` 를 그대로 실행하되, Docker 대신 **대역(stand-in)** 을 썼습니다. 대역은 `backend` 컨테이너 자리에 같은 코드를 운영 모드 + TLS(시험용 인증기관)로 실행하고, `exec`/`run`/`cp` 를 로컬 경로로 바꿔 실행합니다.

| 검증 항목 | 결과 |
|---|---|
| `deploy.sh`: `.env` 생성·64자 비밀키 생성(출력 안 함) → 도메인 입력 안내 → 검사 → 시작 → 내부·HTTPS 상태 확인 | 통과 |
| `deploy.sh` 재실행 시 "이미 배포됨"으로 중단(볼륨 보호) | 통과 |
| HTTPS 회원가입·로그인, 세션 쿠키 `Secure`+`HttpOnly`+`SameSite=Lax` | 통과 |
| Agent → HTTPS 전송 → 실제 측정값 저장, 신뢰할 수 없는 인증서면 전송 거부 | 통과 |
| 사용자 B → A 서버 ID 로 조회·수정·삭제·측정·CSV 전부 404, 비로그인 401 | 통과 |
| 다른 출처의 쓰기 요청 403, 같은 출처 허용 | 통과 |
| Agent 중단 → 32초 후 연결 끊김 + 장애 기록 → 재시작 → 복구·해결 처리 | 통과 |
| `backup.sh`: 실행 중 백업·압축·체크섬 | 통과 |
| `restore.sh`: 안전 백업 → 정지 → 복원 → 재시작, 데이터가 백업 시점으로 | 통과 |
| 손상된 백업·체크섬이 다른 백업은 서비스를 멈추기 전에 거부 | 통과 |
| 백엔드가 실행 중이면 복원 도구가 교체를 거부 | 통과 (대역의 첫 버전이 프로세스를 다 끄지 못했을 때 실제로 이 보호가 작동해 복원을 막음) |
| 재시작 후 로그인 세션·계정·서버·측정값·장애 기록 유지 | 통과 |
| 같은 데이터를 쓰는 두 번째 백엔드 프로세스는 `standby`, 데모 작업 중복 없음 | 통과 |
| `status.sh`, `update.sh`(백업 → 재시작 → 상태 확인), 업데이트 후 데이터 유지 | 통과 |
| `check.sh` 거부: `.env` 권한 644, HTTP 외부 공개, http·와일드카드 Origin, 짧은·빈 비밀키, 잘못된 신뢰 주소, 보관 기간 0 | 통과 |
| 스크립트 출력·백엔드 로그·Agent 로그(16,690자)에 비밀키·비밀번호·Agent 키 없음 | 통과 |

대역으로 바꾼 부분(= 이 검증으로 확인되지 않은 부분): Docker 빌드·컨테이너, nginx, Caddy, 공인 IP 조회, HTTP→HTTPS 리다이렉트 응답, `.env` 권한 값(Windows 는 `chmod 600` 을 반영하지 못해 권한 값만 대역이 답함).

**정적 검토와 기타 확인 (실행)**

| 항목 | 결과 |
|---|---|
| Linux ARM64·AMD64 용 Python 휠(`pip download --platform`) | 백엔드·Agent 의존성 전부 바이너리 휠 있음 (argon2, pydantic-core, psutil, uvloop 계열 포함) |
| 베이스 이미지 아키텍처(Docker Hub API) | `python:3.13-slim`, `node:22-bookworm-slim`, `nginx:1.30-alpine`, `caddy:2-alpine` 모두 `arm64`·`amd64` 제공 |
| npm 네이티브 빌드 도구 | `package-lock.json` 에 rolldown·Tailwind·LightningCSS·TypeScript 의 `linux-arm64-gnu`·`linux-x64-gnu` 포함 |
| ShellCheck 0.11 | 오류·경고 없음(정보성 안내만) |
| compose 구문·변수·신뢰 주소 일관성 | 통과 (docs/DOCKER_VERIFY.md 1장) |

**서버에서만 확인 가능 (미검증)**: Docker 이미지 빌드, Oracle 서버·Security List, `setup-server.sh`, DuckDNS + Let's Encrypt 발급, Caddy·nginx 의 실제 IP 전달과 위조 헤더 무시, 서버 재부팅 후 자동 복구, 유휴 회수 여부.

### 테스트하지 못한 것

- **Docker 관련 전부** — 개발한 PC 에 Docker 가 없어 `Dockerfile` 3개, compose 파일 2개, `nginx.conf.template`, `Caddyfile` 은 **한 번도 빌드·실행하지 못했습니다.** 정적으로 확인한 것과 실행이 필요한 것, 실행할 명령과 성공 기준은 [`docs/DOCKER_VERIFY.md`](docs/DOCKER_VERIFY.md) 에 정리했습니다.
- HTTPS 인증서 발급, systemd 유닛.
- Linux/macOS 에서의 Agent (Windows 에서만 실행).
- PostgreSQL 전환.
- 24시간 이상 연속 운영, 서버 수십 대 규모의 부하.
- 브라우저 화면을 통한 A/B 권한 테스트(권한 검사는 API 에서 이뤄지므로 API 로 검증).

## 10. 운영·유지보수

서버에서의 운영은 `deploy/scripts/` 의 스크립트로 합니다. 모든 스크립트는 실패하면 즉시 중단하고, 비밀값을 출력하지 않으며, **데이터 볼륨을 지우는 명령을 쓰지 않습니다.**

| 작업 | 명령 |
|---|---|
| 상태 확인 | `deploy/scripts/status.sh` |
| 업데이트(코드·`.env` 반영) | `deploy/scripts/update.sh` — 자동 백업 후 다시 빌드 |
| 백업 / 복원 | `deploy/scripts/backup.sh` / `deploy/scripts/restore.sh <파일>` ([docs/BACKUP_RESTORE.md](docs/BACKUP_RESTORE.md)) |
| 로그 | `docker compose logs --tail 100 backend` (서비스당 10MB × 3개로 제한) |

- **보존 기간**: 측정값은 `CLOUDOPS_RETENTION_DAYS`(기본 7일), 해결된 장애 이력은 `CLOUDOPS_INCIDENT_RETENTION_DAYS`(기본 365일)가 지나면 1시간마다 삭제됩니다. 진행 중인 장애는 지우지 않습니다.
- **백그라운드 작업 중복 방지**: 연결 끊김 감시·데모 시뮬레이터·보존 기간 정리는 데이터 볼륨의 잠금 파일을 얻은 프로세스 하나만 실행합니다. 백엔드를 여러 개 띄워도 나머지는 API 만 처리합니다(`/api/v1/health` 의 `background` 가 `running`/`standby` 로 표시).
- **가입 차단**: 본인 계정을 만든 뒤 `.env` 에서 `CLOUDOPS_ALLOW_REGISTRATION=false` 후 `update.sh`.
- **데모 끄기**: `CLOUDOPS_DEMO_MODE=false`. 남아 있는 가상 서버는 갱신이 멈춰 `연결 끊김` 으로 보입니다(대시보드에서 제거 가능).
- **PostgreSQL 전환**: `requirements.txt` 에 `psycopg[binary]` 추가 → `CLOUDOPS_DATABASE_URL=postgresql+psycopg://user:pass@host/db`. 모델은 양쪽에서 동작하도록 작성했지만 실제 전환은 검증하지 않았습니다. 백업 스크립트는 SQLite 전용입니다.

## 11. 기술 선택에 대한 의견

요청하신 스택은 이 규모(서버 수십 대, 사용자 소수)에 적합해서 그대로 사용했습니다. 다만 알아 둘 점:

| 선택 | 판단 |
|---|---|
| SQLite | 서버 20대 × 5초 주기 ≈ 하루 35만 행. WAL 모드로 충분합니다. 쓰기는 동시에 1건만 가능하므로 서버가 수백 대가 되면 PostgreSQL(+TimescaleDB)로 옮겨야 합니다. |
| 직접 만든 시계열 저장 | 학습·포트폴리오 목적에 맞습니다. 실무에서는 Prometheus + Grafana 가 표준이므로, 이 프로젝트 뒤에 그 조합을 써 보면 "왜 그렇게 설계됐는지"가 잘 보입니다. |
| 폴링 (WebSocket 아님) | 3초 폴링은 구현·디버깅·프록시 통과가 단순하고 이 규모에서 부하가 미미합니다. 1초 미만 갱신이나 동시 접속자가 많아지면 SSE/WebSocket 이 낫습니다. |
| passlib 대신 argon2-cffi | passlib 은 유지보수가 멈춰 최신 bcrypt 와 충돌합니다. Argon2id 를 직접 사용했습니다. |
| localStorage 토큰 대신 HttpOnly 쿠키 | XSS 로 토큰이 탈취되는 경로를 막기 위해서입니다. |
