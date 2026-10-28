"""수집 → 상태 → 장애 감지 → 조회/내보내기 흐름 테스트."""
from datetime import timedelta

from app.database import utcnow
from app.models import Incident, Metric, Server
from app.services.alerts import detect_offline
from app.services.metrics import purge_old_metrics

from .conftest import create_server, ingest, make_client, sample


def _server(client, sid):
    return client.get(f"/api/v1/servers/{sid}").json()


def _incidents(client, **params):
    return client.get("/api/v1/incidents", params=params).json()


# ---------- 수집 ----------
def test_ingest_requires_valid_agent_key(client):
    create_server(client)
    anon = make_client()
    assert anon.post("/api/v1/ingest", json=sample()).status_code == 401
    for bad in ("Bearer wrong", "Bearer cops_" + "a" * 43, "Basic abc", "cops_x"):
        assert anon.post("/api/v1/ingest", json=sample(), headers={"Authorization": bad}).status_code == 401


def test_user_session_cannot_be_used_for_ingest(client):
    create_server(client)
    assert client.post("/api/v1/ingest", json=sample()).status_code == 401


def test_ingest_updates_status_and_latest(client):
    server, key = create_server(client)
    assert ingest(key, cpu_percent=12.5).status_code == 202
    s = _server(client, server["id"])
    assert s["status"] == "ok"
    assert s["latest"]["cpu_percent"] == 12.5
    assert s["last_seen_at"] is not None
    assert s["reported_hostname"] == "web-01" and s["agent_version"] == "1.0.0"


def test_ingest_validates_payload(client):
    _, key = create_server(client)
    assert ingest(key, cpu_percent=150).status_code == 422
    assert ingest(key, mem_percent=-1).status_code == 422
    assert ingest(key, disk_used="lots").status_code == 422
    assert ingest(key, command="rm -rf /").status_code == 422  # 알 수 없는 필드는 거부


def test_ingest_rate_limit(client, monkeypatch):
    from app.config import get_settings

    _, key = create_server(client)
    monkeypatch.setattr(get_settings(), "ingest_min_interval_seconds", 5.0)
    assert ingest(key).status_code == 202
    assert ingest(key).status_code == 429


# ---------- 상태 ----------
def test_server_goes_offline_when_data_stops_and_never_shows_ok(client, db):
    server, key = create_server(client)
    ingest(key)
    assert _server(client, server["id"])["status"] == "ok"

    row = db.get(Server, server["id"])
    row.last_seen_at = utcnow() - timedelta(seconds=120)
    db.commit()

    assert _server(client, server["id"])["status"] == "offline"
    summary = client.get("/api/v1/dashboard/summary").json()
    assert summary["offline"] == 1 and summary["ok"] == 0
    assert summary["avg_cpu"] is None  # 끊긴 서버의 옛 값은 평균에 넣지 않는다

    assert detect_offline(db, utcnow()) == 1
    assert detect_offline(db, utcnow()) == 0  # 중복 생성 금지
    open_incidents = _incidents(client, state="open")
    assert [(i["metric"], i["severity"]) for i in open_incidents] == [("offline", "critical")]

    # 데이터가 다시 들어오면 복구되고 연결 끊김 장애는 해결된다
    ingest(key)
    assert _server(client, server["id"])["status"] == "ok"
    resolved = _incidents(client, state="resolved")
    assert len(resolved) == 1 and resolved[0]["resolved_at"] is not None


def test_pending_server_does_not_get_offline_incident(client, db):
    create_server(client)
    assert detect_offline(db, utcnow()) == 0


# ---------- 임계치 장애 ----------
def test_threshold_breach_opens_single_incident_without_duplicates(client, db):
    server, key = create_server(client)
    for cpu in (85, 88, 91, 86):
        ingest(key, cpu_percent=cpu)
    incidents = _incidents(client)
    assert len(incidents) == 1
    assert incidents[0]["metric"] == "cpu" and incidents[0]["severity"] == "warning"
    assert incidents[0]["peak_value"] == 91 and incidents[0]["resolved_at"] is None
    assert _server(client, server["id"])["status"] == "warning"
    assert db.query(Incident).count() == 1


def test_incident_escalates_to_critical(client):
    server, key = create_server(client)
    ingest(key, cpu_percent=85)
    ingest(key, cpu_percent=97)
    incidents = _incidents(client)
    assert len(incidents) == 1 and incidents[0]["severity"] == "critical"
    assert incidents[0]["threshold"] == 95
    assert _server(client, server["id"])["status"] == "critical"


def test_incident_resolves_only_after_consecutive_normal_samples(client):
    server, key = create_server(client)
    ingest(key, mem_percent=90)
    ingest(key, mem_percent=50)
    ingest(key, mem_percent=50)
    assert _incidents(client)[0]["resolved_at"] is None  # 2회로는 부족
    ingest(key, mem_percent=92)  # 다시 초과 → 연속 카운트 초기화, 새 장애는 생기지 않음
    ingest(key, mem_percent=50)
    ingest(key, mem_percent=50)
    assert len(_incidents(client)) == 1 and _incidents(client)[0]["resolved_at"] is None
    ingest(key, mem_percent=50)  # 연속 3회
    incident = _incidents(client)[0]
    assert incident["resolved_at"] is not None and incident["peak_value"] == 92
    assert _server(client, server["id"])["status"] == "ok"

    ingest(key, mem_percent=90)  # 해결 후 재발 → 새 장애
    assert len(_incidents(client)) == 2


def test_each_metric_tracked_independently(client):
    _, key = create_server(client)
    ingest(key, cpu_percent=99, mem_percent=85, disk_percent=96)
    by_metric = {i["metric"]: i["severity"] for i in _incidents(client)}
    assert by_metric == {"cpu": "critical", "memory": "warning", "disk": "critical"}


def test_custom_thresholds_are_used(client):
    _, key = create_server(client, cpu_warn=30, cpu_crit=50)
    ingest(key, cpu_percent=35)
    assert _incidents(client)[0]["threshold"] == 30


def test_incident_filters(client):
    s1, k1 = create_server(client, name="a")
    s2, k2 = create_server(client, name="b")
    ingest(k1, cpu_percent=99)
    ingest(k2, disk_percent=90)
    assert len(_incidents(client)) == 2
    only = _incidents(client, server_id=s2["id"])
    assert len(only) == 1 and only[0]["server_name"] == "b"
    assert _incidents(client, state="resolved") == []
    assert client.get("/api/v1/incidents?limit=9999").status_code == 422


# ---------- 조회 ----------
def test_metric_series_ranges(client, db):
    server, key = create_server(client)
    sid = server["id"]
    now = utcnow()
    base = {k: v for k, v in sample().items() if k not in ("hostname", "os", "agent_version")}
    # 30분 전 근처에서 같은 5분(그리고 같은 30초) 버킷에 들어가도록 정렬한 두 시각
    epoch = int((now - timedelta(seconds=1800)).timestamp())
    aligned = now - timedelta(seconds=now.timestamp() - (epoch - epoch % 300 + 100))
    stamps = (
        (now - timedelta(seconds=30), 10.0), (now - timedelta(seconds=200), 20.0),
        (aligned, 30.0), (aligned + timedelta(seconds=10), 50.0),
        (now - timedelta(seconds=40000), 60.0), (now - timedelta(seconds=100000), 70.0),
    )
    for ts, cpu in stamps:
        db.add(Metric(server_id=sid, ts=ts, **{**base, "cpu_percent": cpu}))
    db.commit()

    def cpus(range_key):
        r = client.get(f"/api/v1/servers/{sid}/metrics", params={"range": range_key})
        assert r.status_code == 200
        return r.json()

    assert [p["cpu_percent"] for p in cpus("1m")["points"]] == [10.0]
    assert [p["cpu_percent"] for p in cpus("5m")["points"]] == [20.0, 10.0]
    assert cpus("5m")["bucket_seconds"] == 0
    hour = cpus("1h")
    assert hour["bucket_seconds"] == 30 and len(hour["points"]) == 3
    day = cpus("24h")
    assert day["bucket_seconds"] == 300
    values = [p["cpu_percent"] for p in day["points"]]
    assert values[0] == 60.0 and 70.0 not in values  # 24시간 밖의 값은 제외
    assert 40.0 in values  # 같은 5분 버킷의 30, 50 은 평균 40 으로 합쳐진다
    assert client.get(f"/api/v1/servers/{sid}/metrics", params={"range": "7d"}).status_code == 422


def test_dashboard_summary_and_timeseries(client):
    _, k1 = create_server(client, name="a")
    _, k2 = create_server(client, name="b")
    create_server(client, name="c")  # 데이터 없음
    ingest(k1, cpu_percent=20, mem_percent=40)
    ingest(k2, cpu_percent=90, mem_percent=60)
    s = client.get("/api/v1/dashboard/summary").json()
    assert (s["total"], s["ok"], s["warning"], s["pending"], s["reporting"]) == (3, 1, 1, 1, 2)
    assert s["avg_cpu"] == 55.0 and s["avg_mem"] == 50.0
    assert s["open_incidents"] == 1 and len(s["recent_incidents"]) == 1
    series = client.get("/api/v1/dashboard/timeseries", params={"range": "5m"}).json()
    assert sum(p["servers"] for p in series["points"]) >= 2


# ---------- 내보내기 / 보존 ----------
def test_csv_export(client):
    server, key = create_server(client, name="=cmd|' /C calc'!A0")
    ingest(key, cpu_percent=99)
    r = client.get(f"/api/v1/servers/{server['id']}/metrics/export", params={"range": "1h"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    lines = r.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("timestamp_utc,data_source,cpu_percent")
    assert len(lines) == 2 and ",agent,99.0," in lines[1]

    r = client.get("/api/v1/incidents/export")
    assert r.status_code == 200
    body = r.text.lstrip("﻿")
    assert "'=cmd" in body  # 수식 삽입 방지: 앞에 ' 가 붙는다
    assert ",agent,cpu,critical," in body


def test_retention_purges_old_metrics(client, db):
    server, key = create_server(client)
    ingest(key)
    base = {k: v for k, v in sample().items() if k not in ("hostname", "os", "agent_version")}
    db.add(Metric(server_id=server["id"], ts=utcnow() - timedelta(days=10), **base))
    db.commit()
    assert purge_old_metrics(db, utcnow(), retention_days=7) == 1
    assert db.query(Metric).count() == 1


def test_data_persists_across_new_db_sessions(client):
    """설정과 기록은 파일 DB 에 저장된다(메모리 아님)."""
    from app.database import SessionLocal

    server, key = create_server(client, cpu_warn=42, cpu_crit=77)
    ingest(key, cpu_percent=50)
    with SessionLocal() as fresh:
        row = fresh.get(Server, server["id"])
        assert (row.cpu_warn, row.cpu_crit) == (42, 77)
        assert fresh.query(Metric).count() == 1 and fresh.query(Incident).count() == 1
