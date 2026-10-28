# 백업과 복원

## 1. 무엇을 백업하나

| 대상 | 위치 | 백업 방법 |
|---|---|---|
| 계정·서버 설정·측정값·장애 이력 | Docker 볼륨 `cloudops-monitor_cloudops-data` 의 `cloudops.db` (SQLite) | `deploy/scripts/backup.sh` |
| 설정 파일 `.env` (비밀키 포함) | `~/cloudops-monitor/.env` | 자동 백업하지 않음 — 아래 4장 |
| HTTPS 인증서 | Docker 볼륨 `caddy-data` | 백업 불필요. 없어지면 Caddy 가 다시 발급 |

## 2. 백업이 "일관된" 이유

실행 중인 SQLite 파일을 `cp` 로 복사하면 쓰기 도중의 반쯤 된 내용이나, 아직 본 파일에 합쳐지지 않은 WAL 파일 내용을 놓칠 수 있다.
`backup.sh` 는 컨테이너 안에서 `python -m app.maintenance backup` 을 실행한다. 이 명령은 다음과 같이 동작한다.

1. SQLite **온라인 백업 API** 로 한 시점의 완전한 사본을 만든다. 서비스를 멈추지 않는다.
2. 사본을 WAL 없이 파일 하나로 완결되게 저장한다.
3. 사본에 `PRAGMA integrity_check` 와 필수 테이블 검사를 실행하고, 테이블별 행 수만 출력한다(비밀번호·키 해시는 출력하지 않음).
4. 호스트의 `backups/` 로 꺼낸 뒤 gzip 압축, SHA-256 체크섬 파일 생성, 권한 600.

## 3. 백업하기 (서버)

```bash
cd ~/cloudops-monitor && deploy/scripts/backup.sh
```

결과

```
backups/cloudops-20261026T031500Z.db.gz
backups/cloudops-20261026T031500Z.db.gz.sha256
```

- 최근 `CLOUDOPS_BACKUP_KEEP`(기본 14)개만 남기고 오래된 것부터 지운다.
- `update.sh` 와 `restore.sh` 는 시작 전에 자동으로 백업한다.
- 매일 자동 백업: `crontab -e` 에 다음을 추가한다.

```
15 3 * * * cd /home/ubuntu/cloudops-monitor && deploy/scripts/backup.sh >> backups/backup.log 2>&1
```

**백업 파일에는 비밀번호 해시와 Agent 키 해시가 들어 있다.** 원문은 아니지만 공개 저장소·메신저·공유 드라이브의 공개 폴더에 올리지 않는다.

## 4. 내 PC 로 내려받기 — 꼭 한다

백업이 서버에만 있으면 서버를 잃을 때 함께 잃는다(무료 서버는 유휴 회수 가능성이 있다 — docs/FREE_DEPLOY.md 1-3).

### 4-1. 내려받기 (Windows PowerShell)

```bash
mkdir $HOME\cloudops-backups -Force
```

```bash
scp -i $HOME\.ssh\oci_cloudops "ubuntu@<서버IP>:cloudops-monitor/backups/cloudops-*.db.gz*" $HOME\cloudops-backups\
```

### 4-2. 손상 여부 확인 (PC)

```bash
Get-ChildItem $HOME\cloudops-backups\*.db.gz | ForEach-Object { $want = (Get-Content "$($_.FullName).sha256").Split(' ')[0]; $got = (Get-FileHash $_.FullName -Algorithm SHA256).Hash.ToLower(); "{0}  {1}" -f ($(if ($want -eq $got) {'OK  '} else {'다름'})), $_.Name }
```

모든 줄이 `OK` 여야 한다.

### 4-3. `.env` 보관

`.env` 의 `CLOUDOPS_SECRET_KEY` 를 잃어도 **데이터는 잃지 않는다.** 새 키로 시작하면 로그인 세션만 끊긴다(다시 로그인하면 됨).
그래도 같은 설정으로 빨리 복구하려면 비밀번호 관리자(예: 1Password, Bitwarden)의 보안 메모에 `.env` 내용을 보관한다. 일반 파일로 PC 에 둔다면 본인만 접근할 수 있는 폴더에 둔다.

## 5. 복원하기 (같은 서버)

```bash
cd ~/cloudops-monitor && deploy/scripts/restore.sh backups/cloudops-20261026T031500Z.db.gz
```

진행 순서

1. 체크섬 확인 (`.sha256` 파일이 옆에 있으면)
2. 서비스를 멈추기 **전에** 백업 파일의 무결성·구조 검사. 깨진 파일이면 여기서 중단하고 아무것도 바꾸지 않는다.
3. `복원` 을 입력해 확인 (`--yes` 로 생략 가능)
4. **현재 데이터를 먼저 백업**(되돌릴 수 있게)
5. backend·frontend 정지 → 복원 → 시작 → 상태 확인

- 복원 도구는 백엔드가 쥐고 있는 잠금을 확인해서, 백엔드가 실행 중이면 교체를 거부한다.
- 교체는 임시 파일에 완성한 뒤 한 번에 바꾼다. 이전 DB 의 WAL/SHM 파일도 함께 지운다.
- 중간에 실패하면 기존 DB 는 그대로이고, 멈췄던 서비스를 다시 시작한다.
- 서비스가 응답하지 않아 4번 백업을 할 수 없을 때만 `--no-safety-backup` 을 붙인다.

## 6. PC 의 백업을 서버로 올려 복원

```bash
scp -i $HOME\.ssh\oci_cloudops $HOME\cloudops-backups\cloudops-20261026T031500Z.db.gz* "ubuntu@<서버IP>:cloudops-monitor/backups/"
```

그다음 서버에서 5장의 명령을 실행한다.

## 7. 새 서버로 옮기기 (서버를 잃었을 때)

1. docs/FREE_DEPLOY.md 3~6장대로 새 서버를 만들고 배포한다(빈 상태로 시작).
2. 6장처럼 PC 의 최신 백업을 새 서버에 올린다.
3. `deploy/scripts/restore.sh backups/<파일> --yes`
4. 새 서버의 공인 IP 가 바뀌었으면 DuckDNS 의 IP 를 바꾼다. Agent 는 도메인으로 접속하므로 다시 설정할 필요가 없다. Agent 키는 DB 와 함께 복원되므로 기존 키가 그대로 동작한다.

## 8. 복원 연습

백업은 복원해 봐야 믿을 수 있다. 한 달에 한 번 정도 다음을 해 본다.

```bash
deploy/scripts/backup.sh && deploy/scripts/restore.sh "$(ls -1t backups/cloudops-*.db.gz | head -n 1)" --yes && deploy/scripts/status.sh
```

복원 직전에 만든 백업으로 되돌리는 것이라 데이터는 바뀌지 않고, 몇 초 동안만 서비스가 멈춘다.
