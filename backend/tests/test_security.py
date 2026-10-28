"""최종 보안 점검: 접근 권한(A/B), Agent 키 범위, 비정상 입력, 비밀정보 노출, 운영 설정."""
import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import Settings, get_settings
from app.models import Incident, Metric, Server, User

from .conftest import create_server, ingest, make_client, register, sample

A_PASSWORD = "user-a-password-123"
B_PASSWORD = "user-b-password-456"
SERVER_BODY = {"name": "hacked", "host": "1.1.1.1"}


@pytest.fixture
def a():
    return register(make_client(), "a@example.com", A_PASSWORD)


@pytest.fixture
def b():
    return register(make_client(), "b@example.com", B_PASSWORD)


def _protected_requests(sid: int):
    """(메서드, 경로, 본문) — A 의 서버 ID 를 직접 넣어 만든 요청 전체."""
    base = f"/api/v1/servers/{sid}"
    return [
        ("GET", base, None),
        ("PUT", base, SERVER_BODY),
        ("DELETE", base, None),
        ("POST", f"{base}/rotate-key", None),
        ("GET", f"{base}/metrics?range=1h", None),
        ("GET", f"{base}/metrics/export?range=24h", None),
    ]


# ---------- 3. 사용자 A / B 접근 권한 ----------
def test_user_b_cannot_reach_user_a_server_by_id(a, b, db):
    server, key = create_server(a, name="a-server")
    sid = server["id"]
    assert ingest(key, cpu_percent=99).status_code == 202  # 측정 기록 + 장애 이력 생성

    for method, path, body in _protected_requests(sid):
        r = b.request(method, path, json=body)
        assert r.status_code == 404, (method, path, r.status_code)
        assert "a-server" not in r.text

    # 장애 이력: 목록·서버 ID 지정·CSV 어디에도 A 의 기록이 나오지 않는다
    assert b.get("/api/v1/incidents").json() == []
    assert b.get(f"/api/v1/incidents?server_id={sid}").json() == []
    for path in ("/api/v1/incidents/export", f"/api/v1/incidents/export?server_id={sid}"):
        csv_text = b.get(path).text
        assert "a-server" not in csv_text and len(csv_text.strip().splitlines()) == 1  # 헤더만
    assert b.get("/api/v1/servers").json() == []
    assert b.get("/api/v1/dashboard/summary").json()["total"] == 0
    assert b.get("/api/v1/dashboard/timeseries?range=1h").json()["points"] == []

    # B 의 시도 뒤에도 A 의 데이터는 그대로다
    db.expire_all()
    row = db.get(Server, sid)
    assert row is not None and row.name == "a-server" and row.host == "192.168.0.10"
    assert db.query(Metric).filter_by(server_id=sid).count() == 1
    assert db.query(Incident).filter_by(server_id=sid).count() == 1
    assert ingest(key).status_code == 202  # B 의 rotate-key 시도가 A 의 키를 무효화하지 못했다
    assert a.get(f"/api/v1/servers/{sid}").json()["name"] == "a-server"


def test_unauthenticated_requests_are_rejected(a, db):
    server, key = create_server(a, name="a-server")
    sid = server["id"]
    ingest(key, cpu_percent=99)
    anon = make_client()

    requests = _protected_requests(sid) + [
        ("GET", "/api/v1/servers", None),
        ("POST", "/api/v1/servers", SERVER_BODY),
        ("GET", "/api/v1/incidents", None),
        ("GET", f"/api/v1/incidents?server_id={sid}", None),
        ("GET", "/api/v1/incidents/export", None),
        ("GET", "/api/v1/dashboard/summary", None),
        ("GET", "/api/v1/dashboard/timeseries", None),
        ("POST", "/api/v1/demo/seed", None),
        ("DELETE", "/api/v1/demo", None),
        ("GET", "/api/v1/auth/me", None),
    ]
    for method, path, body in requests:
        r = anon.request(method, path, json=body)
        assert r.status_code == 401, (method, path, r.status_code)
        assert "a-server" not in r.text

    db.expire_all()
    assert db.get(Server, sid).name == "a-server"


def test_agent_key_is_not_a_user_credential(a):
    """Agent 키를 Bearer 토큰으로 써도 사용자 API 에는 들어갈 수 없다."""
    server, key = create_server(a)
    anon = make_client()
    headers = {"Authorization": f"Bearer {key}"}
    for path in ("/api/v1/servers", f"/api/v1/servers/{server['id']}", "/api/v1/incidents", "/api/v1/auth/me"):
        assert anon.get(path, headers=headers).status_code == 401


# ---------- 4. Agent 키 범위 ----------
def test_agent_key_only_writes_to_its_own_server(a, b, db):
    a_server, a_key = create_server(a, name="a-server")
    a_other, _ = create_server(a, name="a-other")
    b_server, b_key = create_server(b, name="b-server")

    assert ingest(a_key, cpu_percent=11).status_code == 202
    assert ingest(b_key, cpu_percent=22).status_code == 202

    assert db.query(Metric).filter_by(server_id=a_server["id"]).one().cpu_percent == 11
    assert db.query(Metric).filter_by(server_id=b_server["id"]).one().cpu_percent == 22
    assert db.query(Metric).filter_by(server_id=a_other["id"]).count() == 0
    assert a.get(f"/api/v1/servers/{a_other['id']}").json()["status"] == "pending"


@pytest.mark.parametrize("field", ["server_id", "id", "owner_id", "is_demo", "ts"])
def test_agent_cannot_choose_target_server_in_payload(a, b, db, field):
    """수집 대상은 오직 키로 결정된다. 본문에 서버 ID 등을 넣으면 요청 전체를 거부한다."""
    _, a_key = create_server(a, name="a-server")
    b_server, _ = create_server(b, name="b-server")
    r = make_client().post(
        "/api/v1/ingest",
        json={**sample(), field: b_server["id"]},
        headers={"Authorization": f"Bearer {a_key}"},
    )
    assert r.status_code == 422
    r = make_client().post(
        f"/api/v1/ingest?server_id={b_server['id']}", json=sample(cpu_percent=77),
        headers={"Authorization": f"Bearer {a_key}"},
    )
    assert r.status_code == 202  # 쿼리 파라미터는 무시되고 키의 주인(A 서버)에만 기록된다
    assert db.query(Metric).filter_by(server_id=b_server["id"]).count() == 0
    assert b.get(f"/api/v1/servers/{b_server['id']}").json()["status"] == "pending"


def test_key_of_deleted_server_stops_working(a):
    server, key = create_server(a)
    assert ingest(key).status_code == 202
    a.delete(f"/api/v1/servers/{server['id']}")
    assert ingest(key).status_code == 401


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "Bearer",
        "Bearer ",
        "Bearer cops_",
        "Bearer cops_" + "A" * 43,
        "Bearer cops_" + "A" * 500,
        "Bearer not-a-cops-key",
        "Bearer ' OR '1'='1",
        "Basic Y29wczp4",
        "cops_missing_scheme",
    ],
)
def test_wrong_agent_keys_are_rejected(a, db, header):
    create_server(a)
    headers = {} if header is None else {"Authorization": header}
    r = make_client().post("/api/v1/ingest", json=sample(), headers=headers)
    assert r.status_code == 401
    assert db.query(Metric).count() == 0


def test_agent_key_hash_cannot_be_used_as_key(a, db):
    """DB 가 유출돼 해시가 알려져도 그 값으로는 인증할 수 없다."""
    server, _ = create_server(a)
    key_hash = db.get(Server, server["id"]).agent_key_hash
    for candidate in (key_hash, "cops_" + key_hash):
        r = make_client().post(
            "/api/v1/ingest", json=sample(), headers={"Authorization": f"Bearer {candidate}"}
        )
        assert r.status_code == 401


# ---------- 4. 비정상 측정값 ----------
_BIG = 2**63


@pytest.mark.parametrize(
    "override",
    [
        {"cpu_percent": -0.1},
        {"cpu_percent": 100.1},
        {"cpu_percent": 1e308},
        {"mem_percent": 101},
        {"disk_percent": -5},
        {"cpu_percent": "50"},  # 숫자처럼 보이는 문자열
        {"cpu_percent": None},
        {"cpu_percent": True},
        {"cpu_percent": [50]},
        {"cpu_percent": {"value": 50}},
        {"mem_used": -1},
        {"mem_used": 1.5},
        {"mem_total": _BIG},
        {"mem_used": 20 * 1024**3},  # 전체(10GiB)보다 많이 썼다고 보고
        {"disk_used": 200 * 1024**3},  # 전체(100GiB)보다 많이 썼다고 보고
        {"net_sent_rate": -1},
        {"net_recv_rate": 1e13},
        {"net_sent_total": -1},
        {"uptime_seconds": -1},
        {"uptime_seconds": 10**11},
        {"hostname": "h" * 254},
        {"os": "o" * 129},
        {"agent_version": "v" * 33},
        {"hostname": 12345},
        {"unknown_field": 1},
        {"command": "reboot"},
    ],
    ids=lambda o: next(iter(o)) + "=" + repr(next(iter(o.values())))[:24],
)
def test_abnormal_measurements_are_rejected(a, db, override):
    server, key = create_server(a)
    r = ingest(key, **override)
    assert r.status_code == 422, r.text
    assert db.query(Metric).count() == 0 and db.query(Incident).count() == 0
    assert a.get(f"/api/v1/servers/{server['id']}").json()["status"] == "pending"  # 잘못된 값으로는 '수신'도 갱신되지 않는다


@pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
def test_nan_and_infinity_are_rejected(a, db, literal):
    import json

    _, key = create_server(a)
    body = json.dumps(sample()).replace('"cpu_percent": 20.0', f'"cpu_percent": {literal}')
    assert literal in body
    r = make_client().post(
        "/api/v1/ingest", content=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    assert r.status_code == 422
    assert db.query(Metric).count() == 0


@pytest.mark.parametrize("missing", ["cpu_percent", "mem_total", "disk_percent", "uptime_seconds"])
def test_missing_required_fields_are_rejected(a, db, missing):
    _, key = create_server(a)
    body = sample()
    del body[missing]
    r = make_client().post("/api/v1/ingest", json=body, headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 422 and db.query(Metric).count() == 0


@pytest.mark.parametrize("raw", [b"", b"not json", b"[]", b"null", b'"string"', b'{"cpu_percent":'])
def test_malformed_bodies_are_rejected(a, db, raw):
    _, key = create_server(a)
    r = make_client().post(
        "/api/v1/ingest", content=raw,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    assert r.status_code == 422 and db.query(Metric).count() == 0


def test_boundary_values_are_accepted(a, db):
    _, key = create_server(a)
    assert ingest(key, cpu_percent=0, mem_percent=100, disk_percent=100, mem_used=0, net_sent_rate=0).status_code == 202
    assert ingest(key, hostname=None, os=None, agent_version=None).status_code == 202
    assert ingest(key, hostname="evil\x00\nhost").status_code == 202
    assert db.query(Server).one().reported_hostname == "evilhost"  # 제어 문자는 제거 후 저장


# ---------- 5. 비밀정보 노출 ----------
def test_validation_errors_do_not_echo_submitted_values(a):
    anon = make_client()
    secret_pw = "pw-TOO-long-" + "x" * 200
    r = anon.post("/api/v1/auth/register", json={"email": "new@example.com", "password": secret_pw})
    assert r.status_code == 422 and secret_pw not in r.text and "input" not in r.text
    r = anon.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422 and '"short"' not in r.text
    _, key = create_server(a)
    r = ingest(key, hostname="h" * 300)
    assert r.status_code == 422 and "hhhh" not in r.text


def test_secrets_never_appear_in_logs_or_api_responses(a, db, caplog):
    caplog.set_level(logging.DEBUG)
    secret_key = get_settings().secret_key
    server, agent_key = create_server(a, name="a-server")
    sid = server["id"]
    ingest(agent_key, cpu_percent=99)
    ingest("cops_wrong-key-value-000000000000000000000000000")
    rotated = a.post(f"/api/v1/servers/{sid}/rotate-key").json()["agent_key"]
    make_client().post("/api/v1/auth/login", json={"email": "a@example.com", "password": A_PASSWORD})
    make_client().post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong-password-xyz"})

    user = db.query(User).filter_by(email="a@example.com").one()
    key_hash = db.get(Server, sid).agent_key_hash
    session_token = a.cookies.get("cloudops_session")
    secrets_ = [secret_key, A_PASSWORD, "wrong-password-xyz", agent_key, rotated, user.password_hash, session_token]

    for value in secrets_:
        assert value not in caplog.text

    # 평문 키는 발급 응답 한 번뿐. 이후 어떤 조회 응답에도 키·해시·비밀번호 해시가 없다.
    bodies = [
        a.get(path).text
        for path in (
            "/api/v1/auth/me", "/api/v1/servers", f"/api/v1/servers/{sid}", f"/api/v1/servers/{sid}/metrics",
            f"/api/v1/servers/{sid}/metrics/export", "/api/v1/incidents", "/api/v1/incidents/export",
            "/api/v1/dashboard/summary", "/api/v1/config", "/api/v1/health",
        )
    ]
    for body in bodies:
        for value in (secret_key, A_PASSWORD, agent_key, rotated, key_hash, user.password_hash, "password_hash", "agent_key_hash"):
            assert value not in body


def test_public_endpoints_expose_only_non_sensitive_settings():
    anon = make_client()
    health = anon.get("/api/v1/health").json()
    assert health["status"] == "ok" and health["database"] == "ok"
    assert set(health) <= {"status", "database", "background"}  # 상태 외의 정보는 내보내지 않는다
    assert set(anon.get("/api/v1/config").json()) == {"demo_mode", "allow_registration", "offline_after_seconds"}


# ---------- 5. 운영 설정에서 비밀키 누락 ----------
def _settings(monkeypatch, **env):
    for name in ("CLOUDOPS_SECRET_KEY", "CLOUDOPS_ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(Settings, "model_config", {**Settings.model_config, "env_file": None})
    return get_settings.__wrapped__()


@pytest.mark.parametrize("key", [None, "", "short-key", "x" * 31])
def test_production_refuses_to_start_without_strong_secret(monkeypatch, key):
    env = {"CLOUDOPS_ENVIRONMENT": "production"}
    if key is not None:
        env["CLOUDOPS_SECRET_KEY"] = key
    with pytest.raises(RuntimeError, match="CLOUDOPS_SECRET_KEY"):
        _settings(monkeypatch, **env)


def test_production_accepts_strong_secret(monkeypatch):
    s = _settings(monkeypatch, CLOUDOPS_ENVIRONMENT="production", CLOUDOPS_SECRET_KEY="k" * 48)
    assert s.is_production and s.secret_key == "k" * 48


def test_development_uses_random_ephemeral_key_and_warns_without_printing_it(monkeypatch, caplog):
    caplog.set_level(logging.WARNING)
    first = _settings(monkeypatch).secret_key
    second = _settings(monkeypatch).secret_key
    assert len(first) >= 32 and first != second  # 고정된 기본 키가 아니라 매번 새 난수
    assert "CLOUDOPS_SECRET_KEY" in caplog.text
    assert first not in caplog.text and second not in caplog.text


def test_production_process_exits_on_missing_secret_without_serving(tmp_path):
    """실제 프로세스로 확인: 운영 모드 + 비밀키 없음 → import 단계에서 실패하고 서버가 뜨지 않는다."""
    backend_dir = Path(__file__).resolve().parents[1]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLOUDOPS_")}
    env.update(CLOUDOPS_ENVIRONMENT="production", CLOUDOPS_DATABASE_URL=f"sqlite:///{(tmp_path / 'x.db').as_posix()}")
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"], cwd=tmp_path, env={**env, "PYTHONPATH": str(backend_dir)},
        capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace",
    )
    assert result.returncode != 0
    assert "CLOUDOPS_SECRET_KEY" in result.stderr


def test_production_hides_api_docs(monkeypatch):
    from app.main import create_app

    monkeypatch.setattr(get_settings(), "environment", "production")
    from fastapi.testclient import TestClient

    client = TestClient(create_app())
    assert client.get("/api/docs").status_code == 404
    assert client.get("/api/openapi.json").status_code == 404
    assert client.get("/api/v1/health").status_code == 200
