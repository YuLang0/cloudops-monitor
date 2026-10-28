"""서버 운영 기능: 단일 실행 잠금, 상태 확인, Origin 검사, 보존 기간, 백업·복원."""
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest

from app import maintenance
from app.config import get_settings
from app.database import utcnow
from app.main import origin_allowed
from app.models import Incident
from app.services import background
from app.services.locking import SingleInstanceLock
from app.services.metrics import purge_old_incidents

from .conftest import create_server, ingest, make_client, register

BACKEND_DIR = Path(__file__).resolve().parents[1]


# ---------- 단일 실행 잠금 ----------
def test_lock_allows_only_one_holder(tmp_path):
    path = tmp_path / "bg.lock"
    first, second = SingleInstanceLock(path), SingleInstanceLock(path)
    assert first.acquire() is True
    assert second.acquire() is False  # 이미 잡혀 있으면 기다리지 않고 실패
    first.release()
    assert second.acquire() is True  # 풀리면 다른 쪽이 얻을 수 있다
    second.release()


def test_lock_is_released_when_holder_process_dies(tmp_path):
    """비정상 종료(kill)한 프로세스의 잠금은 OS 가 풀어 준다 → 재시작 후 복구 가능."""
    path = tmp_path / "bg.lock"
    code = (
        "import sys, time; sys.path.insert(0, sys.argv[1]);"
        "from app.services.locking import SingleInstanceLock as L;"
        "l = L(sys.argv[2]); print(l.acquire(), flush=True); time.sleep(60)"
    )
    proc = subprocess.Popen([sys.executable, "-c", code, str(BACKEND_DIR), str(path)], stdout=subprocess.PIPE, text=True)
    try:
        assert proc.stdout.readline().strip() == "True"
        assert SingleInstanceLock(path).acquire() is False  # 다른 프로세스가 보유 중
    finally:
        proc.kill()
        proc.wait(timeout=10)
    lock = SingleInstanceLock(path)
    for _ in range(50):
        if lock.acquire():
            break
        time.sleep(0.1)
    assert lock.held
    lock.release()


def test_second_backend_process_runs_api_only(tmp_path, monkeypatch):
    """같은 데이터 폴더를 쓰는 두 번째 프로세스는 감시·데모 작업을 시작하지 않는다."""
    import asyncio

    monkeypatch.setattr(get_settings(), "demo_mode", True)
    path = tmp_path / "bg.lock"
    holder = SingleInstanceLock(path)
    assert holder.acquire()

    async def run():
        lock = SingleInstanceLock(path)
        tasks = background.start_background_tasks(lock)
        state = background.state["background"]
        background.stop_background_tasks(tasks, lock)
        return tasks, state

    tasks, state = asyncio.run(run())
    assert tasks == [] and state == "standby"
    holder.release()

    async def run_owner():
        lock = SingleInstanceLock(path)
        tasks = background.start_background_tasks(lock)
        state = background.state["background"]
        background.stop_background_tasks(tasks, lock)
        return len(tasks), state

    count, state = asyncio.run(run_owner())
    assert count == 3 and state == "running"  # 감시 + 정리 + 데모
    assert background.state["background"] == "stopped"


def test_backend_image_runs_single_worker():
    dockerfile = (BACKEND_DIR / "Dockerfile").read_text(encoding="utf-8")
    assert '"--workers", "1"' in dockerfile


# ---------- 상태 확인 ----------
def test_health_reports_database(anon):
    r = anon.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["database"] == "ok"


def test_health_returns_503_when_database_fails(anon, monkeypatch):
    from sqlalchemy.orm import Session

    def broken(self, *args, **kwargs):
        raise RuntimeError("disk I/O error")

    monkeypatch.setattr(Session, "execute", broken)
    r = anon.get("/api/v1/health")
    assert r.status_code == 503 and r.json() == {"status": "error", "database": "error"}
    assert "disk I/O" not in r.text  # 내부 오류 내용은 밖으로 내보내지 않는다


# ---------- Origin 검사(CSRF 방어) ----------
def test_cross_site_write_requests_are_rejected(client):
    server, _ = create_server(client)
    evil = {"Origin": "https://evil.example.com"}
    assert client.post("/api/v1/servers", json={"name": "x", "host": "1.1.1.1"}, headers=evil).status_code == 403
    assert client.delete(f"/api/v1/servers/{server['id']}", headers=evil).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=evil).status_code == 403
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "x" * 10}, headers={"Origin": "null"}).status_code == 403
    assert client.get(f"/api/v1/servers/{server['id']}").status_code == 200  # 삭제되지 않았다


def test_same_origin_and_agent_requests_are_allowed(client):
    same = {"Origin": "http://testserver"}  # TestClient 의 Host 는 testserver
    r = client.post("/api/v1/servers", json={"name": "x", "host": "1.1.1.1"}, headers=same)
    assert r.status_code == 201
    assert ingest(r.json()["agent_key"]).status_code == 202  # Agent 는 Origin 헤더 없음
    assert client.get("/api/v1/servers", headers={"Origin": "https://evil.example.com"}).status_code == 200  # 읽기는 영향 없음


@pytest.mark.parametrize(
    ("origin", "host", "allowed", "expected"),
    [
        ("https://monitor.example.com", "monitor.example.com", [], True),
        ("http://localhost:5173", "localhost:5173", [], True),
        ("https://MONITOR.example.com", "monitor.example.com", [], True),
        ("https://monitor.example.com.evil.com", "monitor.example.com", [], False),
        ("https://evil.com", "monitor.example.com", [], False),
        ("https://other.example.com", "monitor.example.com", ["https://other.example.com"], True),
        ("null", "monitor.example.com", [], False),
        ("https://monitor.example.com", None, [], False),
    ],
)
def test_origin_allowed(origin, host, allowed, expected):
    assert origin_allowed(origin, host, allowed) is expected


# ---------- 보존 기간 ----------
def test_old_resolved_incidents_are_purged_but_open_ones_kept(client, db):
    server, key = create_server(client)
    sid = server["id"]
    now = utcnow()
    db.add_all([
        Incident(server_id=sid, metric="cpu", severity="warning", started_at=now - timedelta(days=400), resolved_at=now - timedelta(days=399)),
        Incident(server_id=sid, metric="disk", severity="warning", started_at=now - timedelta(days=10), resolved_at=now - timedelta(days=9)),
        Incident(server_id=sid, metric="memory", severity="critical", started_at=now - timedelta(days=500)),  # 진행 중
    ])
    db.commit()
    assert purge_old_incidents(db, now, retention_days=365) == 1
    left = {i.metric for i in db.query(Incident).all()}
    assert left == {"disk", "memory"}


def test_retention_settings_are_validated(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("CLOUDOPS_RETENTION_DAYS", "0")
    with pytest.raises(Exception):
        Settings(_env_file=None)


# ---------- 백업 · 복원 ----------
def _populate(client) -> str:
    server, key = create_server(client, name="backup-me")
    ingest(key, cpu_percent=99)
    return server["id"]


def test_backup_is_consistent_and_verifiable(client, tmp_path):
    _populate(client)
    dst = tmp_path / "b" / "backup.db"
    counts = maintenance.backup(dst)
    assert counts["users"] == 1 and counts["servers"] == 1 and counts["metrics"] == 1 and counts["incidents"] == 1
    assert not dst.with_name("backup.db.partial").exists()
    assert maintenance.verify(dst) == counts
    with sqlite3.connect(dst) as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "delete"  # 파일 하나로 완결
    with pytest.raises(maintenance.MaintenanceError, match="덮어쓰지"):
        maintenance.backup(dst)


def test_backup_while_writes_are_happening(client, tmp_path):
    """쓰기가 계속되는 중에 백업해도 깨지지 않는다."""
    server, key = create_server(client)
    stop = threading.Event()

    def writer():
        while not stop.is_set():
            ingest(key, cpu_percent=10)

    thread = threading.Thread(target=writer)
    thread.start()
    try:
        time.sleep(0.3)
        counts = [maintenance.backup(tmp_path / f"b{i}.db")["metrics"] for i in range(3)]
    finally:
        stop.set()
        thread.join()
    assert counts == sorted(counts) and counts[-1] > 0


@pytest.mark.parametrize("content", [b"", b"not a database at all" * 100])
def test_verify_rejects_broken_files(tmp_path, content):
    bad = tmp_path / "bad.db"
    bad.write_bytes(content)
    with pytest.raises(maintenance.MaintenanceError):
        maintenance.verify(bad)


def test_verify_rejects_other_sqlite_databases(tmp_path):
    other = tmp_path / "other.db"
    with sqlite3.connect(other) as conn:
        conn.execute("CREATE TABLE something (x)")
    with pytest.raises(maintenance.MaintenanceError, match="CloudOps"):
        maintenance.verify(other)


def test_restore_round_trip(client, tmp_path):
    sid = _populate(client)
    snapshot = tmp_path / "snap.db"
    maintenance.backup(snapshot)

    # 백업 이후의 변경: 서버를 하나 더 만들고 원래 서버를 삭제
    create_server(client, name="after-backup")
    client.delete(f"/api/v1/servers/{sid}")

    target = tmp_path / "restored" / "cloudops.db"
    target.parent.mkdir()
    Path(str(target) + "-wal").write_bytes(b"stale wal")  # 남아 있던 WAL 은 지워져야 한다
    counts = maintenance.restore(snapshot, db_path=target, lock_path=tmp_path / "restore.lock")
    assert counts["servers"] == 1
    assert not Path(str(target) + "-wal").exists()
    with sqlite3.connect(target) as conn:
        names = [r[0] for r in conn.execute("SELECT name FROM servers")]
    assert names == ["backup-me"]


def test_restore_refuses_while_backend_holds_lock(client, tmp_path):
    _populate(client)
    snapshot = tmp_path / "snap.db"
    maintenance.backup(snapshot)
    target = tmp_path / "live.db"
    target.write_bytes(b"live data must not be touched")
    running = SingleInstanceLock(tmp_path / "bg.lock")
    assert running.acquire()
    try:
        with pytest.raises(maintenance.MaintenanceError, match="실행 중"):
            maintenance.restore(snapshot, db_path=target, lock_path=tmp_path / "bg.lock")
    finally:
        running.release()
    assert target.read_bytes() == b"live data must not be touched"


def test_restore_refuses_broken_backup_without_touching_db(tmp_path):
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"garbage" * 50)
    target = tmp_path / "live.db"
    target.write_bytes(b"live")
    with pytest.raises(maintenance.MaintenanceError):
        maintenance.restore(bad, db_path=target, lock_path=tmp_path / "x.lock")
    assert target.read_bytes() == b"live"


def test_cli_prints_counts_but_no_secrets(client, tmp_path, capsys):
    register(make_client(), "secret-owner@example.com", "very-secret-password-1")
    _populate(client)
    dst = tmp_path / "cli.db"
    assert maintenance.main(["backup", str(dst)]) == 0
    assert maintenance.main(["verify", str(dst)]) == 0
    out = capsys.readouterr()
    text = out.out + out.err
    assert "users 2" in text
    assert "argon2" not in text and "very-secret-password-1" not in text and "secret-owner" not in text
    assert maintenance.main(["verify", str(tmp_path / "missing.db")]) == 1
