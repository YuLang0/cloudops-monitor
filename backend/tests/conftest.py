from __future__ import annotations

import os
import tempfile
from pathlib import Path

# app 모듈을 import 하기 전에 테스트용 환경변수를 설정한다
_TMP = tempfile.mkdtemp(prefix="cloudops-test-")
os.environ["CLOUDOPS_DATABASE_URL"] = f"sqlite:///{Path(_TMP, 'test.db').as_posix()}"
os.environ["CLOUDOPS_SECRET_KEY"] = "test-secret-key-that-is-long-enough-0123456789"
os.environ["CLOUDOPS_DEMO_MODE"] = "true"
os.environ["CLOUDOPS_INGEST_MIN_INTERVAL_SECONDS"] = "0"
os.environ["CLOUDOPS_OFFLINE_AFTER_SECONDS"] = "30"
os.environ["CLOUDOPS_CLEAR_SAMPLES"] = "3"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.security import login_limiter  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    login_limiter.reset()
    yield


@pytest.fixture
def db():
    with SessionLocal() as session:
        yield session


def make_client() -> TestClient:
    # lifespan 을 실행하지 않으므로(with 문 미사용) 백그라운드 작업은 돌지 않는다 → 테스트가 결정적이다
    return TestClient(app)


@pytest.fixture
def anon() -> TestClient:
    return make_client()


def register(client: TestClient, email: str, password: str = "correct-horse-battery") -> TestClient:
    r = client.post("/api/v1/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return client


@pytest.fixture
def client() -> TestClient:
    return register(make_client(), "alice@example.com")


@pytest.fixture
def other_client() -> TestClient:
    return register(make_client(), "bob@example.com")


def create_server(client: TestClient, **overrides) -> tuple[dict, str]:
    body = {"name": "web-01", "host": "192.168.0.10", "os_name": "Ubuntu 24.04", **overrides}
    r = client.post("/api/v1/servers", json=body)
    assert r.status_code == 201, r.text
    data = r.json()
    return data["server"], data["agent_key"]


def sample(**overrides) -> dict:
    gib = 1024**3
    return {
        "cpu_percent": 20.0, "mem_percent": 40.0, "mem_used": 4 * gib, "mem_total": 10 * gib,
        "disk_percent": 50.0, "disk_used": 50 * gib, "disk_total": 100 * gib,
        "net_sent_rate": 1000.0, "net_recv_rate": 2000.0,
        "net_sent_total": 10_000, "net_recv_total": 20_000,
        "uptime_seconds": 3600, "hostname": "web-01", "os": "Linux 6.8", "agent_version": "1.0.0",
        **overrides,
    }


def ingest(agent_key: str, **overrides):
    return make_client().post(
        "/api/v1/ingest", json=sample(**overrides), headers={"Authorization": f"Bearer {agent_key}"}
    )
