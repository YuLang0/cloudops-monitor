import random
from datetime import timedelta

from app.database import utcnow
from app.models import Incident, Server
from app.services import demo

from .conftest import create_server, ingest, make_client, sample


def test_seed_creates_at_least_three_labelled_demo_servers(client):
    r = client.post("/api/v1/demo/seed")
    assert r.status_code == 201
    servers = r.json()
    assert len(servers) >= 3
    assert all(s["is_demo"] and s["agent_key_prefix"] is None for s in servers)
    assert all(s["latest"] is not None for s in servers if s["name"] != "demo-edge-01")
    assert client.post("/api/v1/demo/seed").status_code == 409
    assert client.get("/api/v1/dashboard/summary").json()["demo"] == len(servers)


def test_demo_servers_are_per_user(client, other_client):
    client.post("/api/v1/demo/seed")
    assert other_client.get("/api/v1/servers").json() == []


def test_demo_tick_writes_samples_and_opens_incidents(client, db):
    client.post("/api/v1/demo/seed")
    before = {s["name"]: s["latest"]["ts"] for s in client.get("/api/v1/servers").json() if s["latest"]}
    # 배치 작업 구간(t % 420 < 75)이면서 엣지 서버가 전송 중인 시각을 고른다
    now = utcnow()
    while not ((now.timestamp() % 420) < 60 and (now.timestamp() % 300) < 200):
        now += timedelta(seconds=5)
    assert demo.tick(db, now, 3.0) == 4
    after = {s["name"]: s for s in client.get("/api/v1/servers").json()}
    assert after["demo-web-01"]["latest"]["ts"] != before["demo-web-01"]
    opened = {(i.server.name, i.metric, i.severity) for i in db.query(Incident).all()}
    assert ("demo-batch-01", "cpu", "critical") in opened
    assert ("demo-edge-01", "disk", "warning") in opened
    assert demo.tick(db, now + timedelta(seconds=3), 3.0) == 4
    assert db.query(Incident).filter_by(metric="cpu", resolved_at=None).count() == 1  # 중복 없음


def test_flaky_profile_goes_silent():
    rng = random.Random(1)
    assert demo.generate_sample("flaky", 100.0, rng) is not None
    assert demo.generate_sample("flaky", 250.0, rng) is None


def test_generated_samples_are_within_valid_ranges():
    rng = random.Random(7)
    for profile in ("web", "db", "batch", "flaky"):
        for t in range(0, 3000, 7):
            s = demo.generate_sample(profile, float(t), rng)
            if s is None:
                continue
            assert 0 <= s["cpu_percent"] <= 100 and 0 <= s["mem_percent"] <= 100
            assert 0 <= s["mem_used"] <= s["mem_total"] and s["net_sent_rate"] >= 0


def test_real_agent_cannot_write_to_demo_server(client, db):
    """가상 서버와 실제 서버의 데이터 경로는 섞이지 않는다."""
    from app.security import generate_agent_key

    client.post("/api/v1/demo/seed")
    demo_server = db.query(Server).filter_by(is_demo=True).first()
    key, demo_server.agent_key_hash, _ = generate_agent_key()  # 누군가 DB 를 조작했더라도
    db.commit()
    r = make_client().post("/api/v1/ingest", json=sample(), headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 401
    assert client.post(f"/api/v1/servers/{demo_server.id}/rotate-key").status_code == 400


def test_remove_demo_keeps_real_servers(client):
    client.post("/api/v1/demo/seed")
    real, key = create_server(client, name="real-01")
    ingest(key)
    assert client.delete("/api/v1/demo").status_code == 204
    remaining = client.get("/api/v1/servers").json()
    assert [s["name"] for s in remaining] == ["real-01"]
    assert remaining[0]["is_demo"] is False
