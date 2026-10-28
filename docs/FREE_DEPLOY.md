# 무료 클라우드 배포 (Oracle Cloud Always Free)

목표: **월 사용료 0원**으로 CloudOps Monitor 를 인터넷에 HTTPS 로 공개하고, 내 PC 의 Agent 를 연결한다.

```
내 PC (agent.py) ──HTTPS──▶ 내이름.duckdns.org ─▶ Oracle 무료 서버 (Ubuntu)
브라우저 ─────────HTTPS──▶                        └ Docker: Caddy(443) → nginx → FastAPI → SQLite(볼륨)
```

> 이 문서의 무료 조건은 **2026-10-26** 에 Oracle 공식 문서에서 확인한 내용이다. 무료 한도는 바뀔 수 있으므로
> 서버를 만들기 전에 1장 마지막의 방법으로 **내 계정 화면에 표시되는 한도**를 직접 확인한다.
> (작성자는 사용자 계정에 접근할 수 없어 계정 화면은 확인하지 못했다.)

---

## 1. 무료 조건

### 1-1. 이 배포에 쓰는 Always Free 자원

| 자원 | Always Free 한도 (공식 문서 기준) | 이 배포의 사용량 |
|---|---|---|
| Arm 서버 (Ampere A1, `VM.Standard.A1.Flex`) | 테넌시 전체 **월 1,500 OCPU 시간 + 9,000 GB 시간 = 상시 2 OCPU · 12 GB**. 1~2대로 나눠 쓸 수 있음. **홈 리전에서만** 생성 | **1 OCPU · 6 GB 1대** (권장) |
| AMD 서버 (`VM.Standard.E2.1.Micro`) — A1 을 못 만들 때 대안 | 최대 2대, 각 1/8 OCPU · 1 GB · 인터넷 50 Mbps | 대안으로만 |
| 부트·블록 볼륨 | 합계 **200 GB**, 볼륨 백업 5개 | 부트 볼륨 기본값(약 50 GB) 1개 |
| 아웃바운드 데이터 전송 | 월 10 TB | 매우 적음 |
| VCN(가상 네트워크) | Free Tier 는 2개까지 | 1개 |
| 공인 IPv4 | 인스턴스 VNIC 에 붙는 임시(ephemeral) 공인 IP | 1개 |

> 예전 글에 자주 나오는 **"A1 4 OCPU · 24 GB 무료"는 현재 문서와 다르다.** 현재 문서는 2 OCPU · 12 GB 다.

### 1-2. 돈이 나가거나 나중에 지워질 수 있는 것 — 하지 않는다

| 하지 않을 것 | 이유 |
|---|---|
| **계정 업그레이드(Pay As You Go 전환)** | 업그레이드하면 무료 한도를 넘는 사용분이 청구된다. 이 배포는 업그레이드 없이 진행한다 |
| 콘솔에서 **"Always Free-eligible" 표시가 없는** 모양(shape)·이미지 선택 | 체험 크레딧($300, 30일)으로만 돌아가다가 체험이 끝나면 멈추거나 삭제된다 |
| A1 합계 2 OCPU · 12 GB 초과 | 초과분은 체험 종료 후 비활성화·삭제 대상 |
| 홈 리전이 아닌 리전에 자원 생성 | Always Free 는 홈 리전에서만 적용 |
| 로드밸런서·추가 블록 볼륨·유료 도메인 구매 | 이 구성에는 필요 없다(Caddy 가 HTTPS 를 처리하고, 도메인은 무료 서브도메인 사용) |
| 예약(reserved) 공인 IP | 필요 없다(임시 공인 IP 로 충분) |

**예산 알림에 대해:** Oracle 의 Budget(예산) 알림은 금액이 기준을 넘었을 때 **메일을 보낼 뿐, 과금을 막지 않는다.**
과금을 막는 것은 "업그레이드하지 않는 것"과 "Always Free 표시가 있는 자원만 만드는 것"이다.

### 1-3. 알고 있어야 할 위험

| 위험 | 내용 | 대응 |
|---|---|---|
| **유휴 인스턴스 회수** | Oracle 은 7일 동안 CPU(95번째 백분위수)·네트워크·메모리(A1 만) 사용률이 모두 20% 미만인 Always Free 인스턴스를 회수(정지)할 수 있다고 공지한다. **이 앱은 평소 부하가 낮아 이 기준에 걸릴 수 있다.** | 백업을 **내 PC 에 정기적으로 내려받는다**(docs/BACKUP_RESTORE.md). 정지되면 콘솔에서 다시 시작한다. 사용률을 올리려고 의미 없는 부하를 돌리는 방법은 권하지 않는다 |
| 계정 장기 미사용 | 30일 이상 사용 흔적이 없는 계정은 정지·해지 대상이 될 수 있다 | 한 달에 한 번 이상 콘솔에 로그인 |
| A1 재고 부족 | 생성 시 `Out of host capacity` 오류가 날 수 있다 | 다른 가용 도메인(AD)을 고르거나 시간을 두고 다시 시도. **유료 모양으로 바꾸지 않는다.** 계속 안 되면 AMD Micro(1 GB)로 진행 |
| 지원 | Always Free 만 쓰는 고객은 Oracle 기술 지원 대상이 아니다 | 이 문서와 커뮤니티 문서로 해결 |

### 1-4. 내 계정의 실제 한도 확인 방법 (직접)

1. 콘솔 왼쪽 위 메뉴 → **Governance & Administration → Tenancy Management → Limits, Quotas and Usage**
2. Service: **Compute**, Scope: 홈 리전의 가용 도메인 선택
3. `Standard.A1 Core Count`(OCPU), `Standard.A1 Memory Count`(GB) 의 **Service Limit / Usage / Available** 확인
4. 서버 생성 화면에서 Shape 와 Image 옆에 **"Always Free-eligible"** 표시가 있는지 확인

출처: [Oracle Always Free Resources](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm), [Oracle Cloud Free Tier 문서](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier.htm)

---

## 2. 계정 만들기 — 직접 진행

비밀번호·카드 정보·SSH 개인키는 **누구에게도(채팅 포함) 보내지 않는다.**

1. <https://signup.cloud.oracle.com> 에서 가입한다. 본인 인증용으로 휴대폰 번호와 카드가 필요하다.
   Oracle 문서에 따르면 **업그레이드하지 않으면 카드에 청구되지 않는다.** 카드 확인을 위해 일시적인 승인 보류(authorization hold)가 생길 수 있다.
2. **홈 리전(Home Region)은 가입 후 바꿀 수 없다.** Always Free 서버는 홈 리전에만 만들 수 있으므로 신중히 고른다.
   한국에서는 `South Korea Central (Seoul)` 을 권장한다. 공식 문서의 A1 가용 도메인 안내에 `South Korea North (Chuncheon)` 이 예외로 적혀 있어, 춘천은 A1 생성에 제약이 있을 수 있다.
3. 가입하면 30일짜리 체험 크레딧이 함께 생긴다. **이 크레딧에 의존하는 자원은 만들지 않는다**(1-2 표).
4. 가입 직후 **업그레이드 안내가 나와도 누르지 않는다.**

---

## 3. 서버 만들기

### 3-1. SSH 키 만들기 (내 PC, 한 번만)

Windows PowerShell:

```bash
ssh-keygen -t ed25519 -f $HOME\.ssh\oci_cloudops -C cloudops
```

- `oci_cloudops` (개인키) 는 내 PC 에만 둔다. **절대 업로드·공유하지 않는다.**
- 다음 단계에서 Oracle 에 올리는 것은 `oci_cloudops.pub` (공개키) 뿐이다.

### 3-2. 인스턴스 생성 (콘솔)

메뉴 → **Compute → Instances → Create instance**

| 항목 | 선택 |
|---|---|
| Name | `cloudops` |
| Placement | 홈 리전의 가용 도메인. 재고 부족 오류가 나면 다른 AD 로 |
| Image | **Canonical Ubuntu 24.04** (Always Free-eligible 표시 확인. 일반 Ubuntu, Minimal 아님) |
| Shape | **Ampere → VM.Standard.A1.Flex, OCPU 1, Memory 6 GB** (Always Free-eligible 확인). 합계 2 OCPU · 12 GB 이하면 늘려도 무료 |
| Networking | "Create new virtual cloud network" + "Create new public subnet", **Assign a public IPv4 address: 예** |
| SSH keys | "Upload public key files" → `oci_cloudops.pub` |
| Boot volume | 기본값 그대로 (약 50 GB, 200 GB 무료 한도 안) |

생성 후 인스턴스 화면에서 **Public IP address** 를 메모한다(이하 `<서버IP>`).

A1 을 계속 만들 수 없으면: Shape 를 **VM.Standard.E2.1.Micro** (AMD, 1 GB, Always Free-eligible) 로 바꾼다.
`setup-server.sh` 가 2 GB 스왑을 만들어 빌드가 가능하게 하지만, 첫 빌드가 오래 걸린다(수십 분).

---

## 4. 방화벽

Oracle 은 방화벽이 **두 겹**이다. 둘 다 열어야 한다.

### 4-1. 클라우드 방화벽 (Security List) — 콘솔에서 직접

Instance → Primary VNIC 의 Subnet → **Security Lists → Default Security List → Ingress Rules**

| 포트 | Source CIDR | 용도 |
|---|---|---|
| 22 (TCP) | **`<내 공인IP>/32`** (기본 규칙 `0.0.0.0/0` 을 이렇게 수정) | SSH 를 내 IP 에서만 |
| 80 (TCP) | `0.0.0.0/0` | Let's Encrypt 인증서 발급 확인 + HTTPS 로 넘기는 리다이렉트 |
| 443 (TCP) | `0.0.0.0/0` | 서비스(HTTPS) |

- 내 공인 IP 확인: 브라우저에서 <https://checkip.amazonaws.com>
- 가정용 인터넷은 공인 IP 가 가끔 바뀐다. SSH 가 안 되면 이 규칙의 IP 를 새 주소로 고친다(콘솔 웹에서 가능하므로 잠기지 않는다).
- **8080, 8000 은 열지 않는다.** API(8000)와 nginx(8080)는 서버 밖으로 공개되지 않게 구성되어 있다.

### 4-2. 서버 안 방화벽 (iptables)

Oracle 의 Ubuntu 이미지는 22번 외의 포트를 서버 안에서도 막아 둔다. 6장의 `setup-server.sh` 가 80/443 허용을 추가하고 재부팅 후에도 유지되게 저장한다.

---

## 5. 무료 도메인 (DuckDNS)

HTTPS 인증서는 IP 주소가 아니라 **도메인 이름**에 발급된다. 도메인을 사지 않고 무료 서브도메인을 쓴다.

**DuckDNS** (<https://www.duckdns.org>, 2026-10-26 확인)

- 무료. GitHub·Google·Reddit 등 계정으로 로그인
- `내이름.duckdns.org` 형식, IPv4 만 지원(IPv6 미지원)
- `duckdns.org` 는 [Public Suffix List](https://publicsuffix.org/) 에 등록돼 있어, Let's Encrypt 발급 횟수 제한이 **서브도메인마다 따로** 적용된다(다른 사용자의 발급이 내 발급을 막지 않음)
- 서비스 약관과 남용 금지 정책을 따른다

순서

1. DuckDNS 에 로그인 → 원하는 이름 입력 → **add domain**
2. **current ip** 칸에 `<서버IP>` 입력 → **update ip**
3. 화면 위의 **token** 은 비밀값이다. 서버의 `.env` 에만 넣는다(선택, `duckdns-update.sh` 용).

확인 (내 PC PowerShell):

```bash
nslookup 내이름.duckdns.org
```

`<서버IP>` 가 나오면 된다.

> `sslip.io`, `nip.io` 같은 "IP 를 이름으로 바꿔 주는" 서비스도 있지만 Public Suffix List 에 없어서
> 전 세계 사용자가 Let's Encrypt 발급 한도를 함께 쓴다(2026-10-26 확인). 발급이 자주 막히므로 권하지 않는다.

---

## 6. 배포

### 6-1. 프로젝트 올리기 (내 PC PowerShell)

ZIP 이 있는 폴더에서:

```bash
scp -i $HOME\.ssh\oci_cloudops cloudops-monitor.zip ubuntu@<서버IP>:~
```

```bash
ssh -i $HOME\.ssh\oci_cloudops ubuntu@<서버IP>
```

### 6-2. 서버 준비 (서버, 한 번만)

```bash
sudo apt-get update && sudo apt-get install -y unzip
```

```bash
unzip -q cloudops-monitor.zip && cd cloudops-monitor && chmod +x deploy/scripts/*.sh
```

```bash
sudo deploy/scripts/setup-server.sh
```

Docker 설치, 부팅 시 자동 시작, 80/443 허용, (메모리가 작으면) 스왑, 보안 업데이트 자동 설치를 한다.
끝나면 **`exit` 로 접속을 끊었다가 다시 SSH 로 접속**한다(docker 그룹 적용).

### 6-3. 첫 배포 (서버)

```bash
cd ~/cloudops-monitor && deploy/scripts/deploy.sh
```

처음에는 `.env` 를 만들고 **비밀키를 자동 생성**(화면에 출력하지 않음, 권한 600)한 뒤 도메인을 넣으라고 안내하며 멈춘다.

```bash
nano .env
```

`CLOUDOPS_DOMAIN=내이름.duckdns.org` 를 채우고 저장(Ctrl+O, Enter, Ctrl+X)한 뒤 다시:

```bash
deploy/scripts/deploy.sh
```

`deploy.sh` 가 하는 일

1. `check.sh` — OS·CPU 구조·메모리·디스크·Docker·Compose 버전·`.env` 권한·비밀키 길이(값은 출력 안 함)·도메인 DNS 가 이 서버를 가리키는지·내부 주소 설정을 검사. 오류가 있으면 멈춘다.
2. 이미지 빌드 — 프론트엔드는 프로덕션 빌드, ARM64 서버에서는 ARM64 이미지로 빌드된다.
3. 시작 → 컨테이너 안 상태 확인(nginx → FastAPI → DB) → `https://도메인` 상태 확인(인증서 발급 포함)

성공하면 `배포 완료: https://내이름.duckdns.org` 가 나온다.

### 6-4. HTTPS 전에는 비밀번호·키가 평문으로 오가지 않는 이유

- 외부에 열리는 포트는 **Caddy 의 80/443 뿐**이다. nginx(8080)는 `127.0.0.1` 에만 묶여 있고, FastAPI(8000)는 컨테이너 내부 전용이다.
- Caddy 의 80번 포트는 **HTTPS 주소로 넘기는 리다이렉트만** 한다. 인증서가 아직 없을 때도 로그인 화면이나 API 를 HTTP 로 제공하지 않는다.
- Agent 는 `localhost` 가 아닌 주소에 `http://` 로 보내려 하면 실행을 거부한다.
- 세션 쿠키는 HTTPS 구성에서 `Secure` 가 강제되어 HTTP 로는 전송되지 않는다.

### 6-5. 첫 계정과 가입 닫기

1. 브라우저에서 `https://내이름.duckdns.org` → 회원가입
2. 서버에서 가입을 닫는다:

```bash
sed -i 's/^CLOUDOPS_ALLOW_REGISTRATION=.*/CLOUDOPS_ALLOW_REGISTRATION=false/' .env && deploy/scripts/update.sh
```

3. 첫 백업 (docs/BACKUP_RESTORE.md):

```bash
deploy/scripts/backup.sh
```

---

## 7. Agent 연결 (내 PC)

1. 웹에서 **서버 등록** → Agent 인증키(`cops_…`)가 **한 번만** 표시된다. 복사해 둔다(채팅·메신저에 붙여 넣지 않는다).
2. ZIP 안의 `agent/agent.py` 가 있는 폴더에서 (Windows PowerShell):

```bash
pip install psutil
```

```bash
$env:CLOUDOPS_URL = "https://내이름.duckdns.org"; $env:CLOUDOPS_AGENT_KEY = Read-Host "Agent 키"; python agent.py --once
```

`Read-Host` 로 입력하면 키가 명령 기록에 남지 않는다. `--once` 가 오류 없이 끝나면 연결 성공이며, 이어서 `python agent.py` 로 계속 실행한다.

3. 웹 화면에서 서버 상태가 "데이터 대기" → "정상"으로 바뀌는지 확인한다. Agent 를 끄면 30초 뒤 "연결 끊김"이 된다.

Linux 서버를 상시 감시하려면 `agent/cloudops-agent.service` 주석의 systemd 설정을 따른다.

---

## 8. 운영

| 작업 | 명령 (서버의 `~/cloudops-monitor` 에서) |
|---|---|
| 상태 확인 | `deploy/scripts/status.sh` |
| 설정·코드 반영 | `deploy/scripts/update.sh` (자동 백업 후 다시 빌드·시작) |
| 백업 / 복원 | `deploy/scripts/backup.sh` / `deploy/scripts/restore.sh <파일>` |
| 로그 | `docker compose logs --tail 100 backend` (서비스: backend, frontend, caddy) |
| 서버 재부팅 후 | 할 일 없음. Docker 가 부팅 시 시작되고 컨테이너는 `restart: unless-stopped` 로 자동 복구 |

**새 버전 올리기:** 새 ZIP 을 6-1 처럼 올린 뒤 서버에서

```bash
cd ~ && unzip -oq cloudops-monitor.zip && cd cloudops-monitor && chmod +x deploy/scripts/*.sh && deploy/scripts/update.sh
```

`.env`, `backups/`, 데이터 볼륨은 ZIP 에 없으므로 덮어써지지 않는다.

**매일 자동 백업 (선택):** `crontab -e` 에 추가

```
15 3 * * * cd /home/ubuntu/cloudops-monitor && deploy/scripts/backup.sh >> backups/backup.log 2>&1
```

### 디스크가 계속 늘지 않게 하는 장치

| 항목 | 한도 |
|---|---|
| 측정값 | `CLOUDOPS_RETENTION_DAYS`(기본 7일) 지난 기록은 1시간마다 삭제. PC 1대 5초 주기 ≈ 하루 1.7만 행 → 7일치 수십 MB |
| 장애 이력 | 해결된 지 `CLOUDOPS_INCIDENT_RETENTION_DAYS`(기본 365일) 지난 기록 삭제. 진행 중인 장애는 남김 |
| 컨테이너 로그 | 서비스당 10 MB × 3개 |
| 백업 | `CLOUDOPS_BACKUP_KEEP`(기본 14개) |
| 이전 이미지 | `update.sh` 가 이름 없는 이미지를 정리 |

SQLite 는 지운 행의 공간을 파일 안에서 재사용하므로, 보관 기간이 일정하면 파일 크기도 일정 수준에서 멈춘다.

---

## 9. 보안 설정 요약

| 항목 | 설정 |
|---|---|
| 운영 비밀키 | `deploy.sh` 가 64자 난수 생성, `.env` 권한 600. 없거나 32자 미만이면 compose 와 백엔드가 모두 **시작을 거부** |
| 쿠키 | `HttpOnly`, `SameSite=Lax`, HTTPS 구성에서 `Secure` 강제 |
| 허용 Origin | 기본은 같은 도메인만. 다른 출처에서 온 쓰기 요청(POST/PUT/DELETE)은 403. CORS 는 `CLOUDOPS_CORS_ORIGINS` 에 `https://` 출처를 명시할 때만 |
| 프록시 신뢰 | Caddy(고정 IP 1개) → nginx 는 Caddy 만 신뢰 → FastAPI 는 nginx(고정 IP 1개)만 신뢰. 와일드카드 신뢰 없음 |
| 공개 포트 | 80(리다이렉트), 443 만. SSH 22 는 내 IP 로 제한 |
| 백그라운드 작업 | 백엔드 워커 1개 + 데이터 볼륨의 잠금 파일로 연결 끊김 감시·데모·정리 작업을 한 프로세스만 실행 |
| 상태 확인 | `/api/v1/health` 가 DB 에 실제 질의. 실패 시 503. 비밀정보 없음 |

---

## 10. 문제 해결

| 증상 | 확인 |
|---|---|
| `check.sh`: 도메인이 다른 IP 를 가리킴 | DuckDNS 의 current ip 를 서버 공인 IP 로 고치고 몇 분 기다림 |
| HTTPS 확인 실패 | Security List 의 80/443 규칙, `sudo iptables -L INPUT -n --line-numbers` 에서 80/443 ACCEPT 가 REJECT 보다 위인지, `docker compose logs caddy` |
| 빌드 중 멈춤·`Killed` | 메모리 부족. `free -h` 로 스왑 확인, `sudo deploy/scripts/setup-server.sh` 재실행 |
| `Pool overlaps with other one on this address space` | `.env` 에서 `CLOUDOPS_APP_SUBNET`·`CLOUDOPS_NGINX_IP` 또는 `CLOUDOPS_EDGE_SUBNET`·`CLOUDOPS_CADDY_IP` 를 짝 맞춰 변경 |
| 로그인 실패 제한이 모든 사용자에게 함께 걸림 | 백엔드 로그(`docker compose logs backend | grep auth/login`)에 사용자 IP 가 아니라 172.x 가 찍히면 신뢰 주소 설정 불일치 (docs/DOCKER_VERIFY.md 3-9) |
| 인스턴스가 정지됨 | 유휴 회수 가능성. 콘솔에서 Start. 디스크가 남아 있으면 데이터도 그대로. 회수로 삭제됐다면 새 서버에 배포 후 PC 의 백업으로 복원 |

---

## 11. 검증 상태 (2026-10-26)

| 구분 | 항목 |
|---|---|
| **이 PC 에서 실제로 실행해 확인** | 백엔드·프론트엔드 테스트, 배포 스크립트 전체 흐름(Docker 대신 로컬 프로세스 대역 사용), 운영 모드 백엔드의 HTTPS 로그인·Agent 전송(시험용 인증서), 사용자 분리, 연결 끊김 감지·복구, 재시작 후 유지, 백업·복원, 두 번째 백엔드 프로세스의 작업 중복 방지, ARM64·AMD64 용 Python 패키지와 베이스 이미지 존재 |
| **실제 서버에서만 확인 가능 (미검증)** | Docker 이미지 빌드, Oracle 서버 생성·방화벽, DuckDNS + Let's Encrypt 인증서 발급, Caddy·nginx 실제 동작(실제 IP 전달·위조 헤더 무시), `setup-server.sh`, 재부팅 후 자동 복구, 유휴 회수 여부 |

자세한 결과는 README 9장과 docs/DOCKER_VERIFY.md 에 있다.
