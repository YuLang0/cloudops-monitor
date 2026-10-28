import pytest

from app.models import Server
from app.security import hash_agent_key

from .conftest import create_server, ingest


def test_create_server_returns_key_once_and_stores_only_hash(client, db):
    server, key = create_server(client)
    assert key.startswith("cops_") and len(key) > 40
    row = db.get(Server, server["id"])
    assert row.agent_key_hash == hash_agent_key(key)
    assert key not in (row.agent_key_hash, row.agent_key_prefix)
    # 이후 조회에서는 평문 키가 절대 나오지 않는다
    assert key not in client.get(f"/api/v1/servers/{server['id']}").text
    assert key not in client.get("/api/v1/servers").text


def test_new_server_is_pending_not_ok(client):
    server, _ = create_server(client)
    assert server["status"] == "pending"
    assert server["last_seen_at"] is None
    assert server["latest"] is None
    assert server["is_demo"] is False


def test_update_and_delete_server(client):
    server, _ = create_server(client)
    body = {"name": "web-renamed", "host": "web.internal.example.com", "os_name": "Debian 12",
            "description": "프론트", "cpu_warn": 60, "cpu_crit": 90, "mem_warn": 70, "mem_crit": 90,
            "disk_warn": 75, "disk_crit": 90}
    r = client.put(f"/api/v1/servers/{server['id']}", json=body)
    assert r.status_code == 200
    assert r.json()["name"] == "web-renamed" and r.json()["cpu_warn"] == 60

    assert client.delete(f"/api/v1/servers/{server['id']}").status_code == 204
    assert client.get(f"/api/v1/servers/{server['id']}").status_code == 404
    assert client.get("/api/v1/servers").json() == []


@pytest.mark.parametrize(
    "host",
    ["http://169.254.169.254/latest", "10.0.0.1; rm -rf /", "$(whoami)", "a b", "../etc/passwd",
     "host`id`", "-bad.example.com", "x" * 300, ""],
)
def test_invalid_host_rejected(client, host):
    r = client.post("/api/v1/servers", json={"name": "x", "host": host})
    assert r.status_code == 422


@pytest.mark.parametrize("host", ["10.0.0.5", "2001:db8::1", "web-01", "db.internal.example.com"])
def test_valid_host_accepted(client, host):
    assert client.post("/api/v1/servers", json={"name": "x", "host": host}).status_code == 201


def test_invalid_names_and_thresholds_rejected(client):
    base = {"name": "x", "host": "10.0.0.1"}
    assert client.post("/api/v1/servers", json={**base, "name": "   "}).status_code == 422
    assert client.post("/api/v1/servers", json={**base, "name": "a" * 65}).status_code == 422
    assert client.post("/api/v1/servers", json={**base, "cpu_warn": 95, "cpu_crit": 80}).status_code == 422
    assert client.post("/api/v1/servers", json={**base, "mem_warn": 0}).status_code == 422
    assert client.post("/api/v1/servers", json={**base, "disk_crit": 101}).status_code == 422


def test_users_cannot_see_or_modify_each_others_servers(client, other_client):
    server, key = create_server(client)
    sid = server["id"]
    ingest(key, cpu_percent=99)

    assert other_client.get("/api/v1/servers").json() == []
    assert other_client.get(f"/api/v1/servers/{sid}").status_code == 404
    assert other_client.get(f"/api/v1/servers/{sid}/metrics").status_code == 404
    assert other_client.get(f"/api/v1/servers/{sid}/metrics/export").status_code == 404
    assert other_client.put(f"/api/v1/servers/{sid}", json={"name": "hacked", "host": "1.1.1.1"}).status_code == 404
    assert other_client.delete(f"/api/v1/servers/{sid}").status_code == 404
    assert other_client.post(f"/api/v1/servers/{sid}/rotate-key").status_code == 404
    assert other_client.get("/api/v1/incidents").json() == []
    assert other_client.get(f"/api/v1/incidents?server_id={sid}").json() == []
    assert other_client.get("/api/v1/dashboard/summary").json()["total"] == 0
    assert other_client.get("/api/v1/dashboard/timeseries").json()["points"] == []
    # 원래 주인은 그대로 볼 수 있다
    assert client.get(f"/api/v1/servers/{sid}").json()["name"] == "web-01"


def test_rotate_key_invalidates_old_key(client):
    server, old_key = create_server(client)
    assert ingest(old_key).status_code == 202
    r = client.post(f"/api/v1/servers/{server['id']}/rotate-key")
    new_key = r.json()["agent_key"]
    assert new_key != old_key
    assert ingest(old_key).status_code == 401
    assert ingest(new_key).status_code == 202


def test_deleting_server_removes_metrics_and_incidents(client, db):
    from app.models import Incident, Metric

    server, key = create_server(client)
    ingest(key, cpu_percent=99)
    assert db.query(Metric).count() == 1 and db.query(Incident).count() == 1
    client.delete(f"/api/v1/servers/{server['id']}")
    db.expire_all()
    assert db.query(Metric).count() == 0 and db.query(Incident).count() == 0
