from app.models import User
from app.security import COOKIE_NAME

from .conftest import make_client, register

PW = "correct-horse-battery"


def test_register_sets_httponly_cookie_and_me_works(anon):
    r = anon.post("/api/v1/auth/register", json={"email": "Alice@Example.com", "password": PW})
    assert r.status_code == 201
    assert r.json()["email"] == "alice@example.com"
    assert "password" not in r.text
    set_cookie = r.headers["set-cookie"].lower()
    assert COOKIE_NAME in set_cookie and "httponly" in set_cookie and "samesite=lax" in set_cookie
    assert anon.get("/api/v1/auth/me").json()["email"] == "alice@example.com"


def test_password_is_stored_as_argon2_hash(client, db):
    user = db.query(User).one()
    assert user.password_hash.startswith("$argon2id$")
    assert PW not in user.password_hash


def test_duplicate_email_rejected(client):
    r = make_client().post("/api/v1/auth/register", json={"email": "alice@example.com", "password": PW})
    assert r.status_code == 409


def test_weak_password_and_bad_email_rejected(anon):
    assert anon.post("/api/v1/auth/register", json={"email": "a@example.com", "password": "short"}).status_code == 422
    assert anon.post("/api/v1/auth/register", json={"email": "not-an-email", "password": PW}).status_code == 422


def test_login_logout_flow(client):
    fresh = make_client()
    assert fresh.get("/api/v1/auth/me").status_code == 401
    assert fresh.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PW}).status_code == 200
    assert fresh.get("/api/v1/auth/me").status_code == 200
    assert fresh.post("/api/v1/auth/logout").status_code == 204
    assert fresh.get("/api/v1/auth/me").status_code == 401


def test_wrong_password_and_unknown_user_get_same_error(client):
    fresh = make_client()
    wrong = fresh.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong-password"})
    unknown = fresh.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_is_rate_limited_after_repeated_failures(client):
    fresh = make_client()
    for _ in range(5):
        r = fresh.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": "wrong-password"})
        assert r.status_code == 401
    # 6번째부터는 비밀번호가 맞아도 차단
    r = fresh.post("/api/v1/auth/login", json={"email": "alice@example.com", "password": PW})
    assert r.status_code == 429


def test_tampered_token_rejected(anon):
    anon.cookies.set(COOKIE_NAME, "eyJhbGciOiJub25lIn0.eyJzdWIiOiIxIn0.")
    assert anon.get("/api/v1/auth/me").status_code == 401


def test_protected_endpoints_require_login(anon):
    for path in ("/api/v1/servers", "/api/v1/incidents", "/api/v1/dashboard/summary",
                 "/api/v1/dashboard/timeseries", "/api/v1/incidents/export",
                 "/api/v1/servers/1", "/api/v1/servers/1/metrics", "/api/v1/servers/1/metrics/export"):
        assert anon.get(path).status_code == 401, path
    assert anon.post("/api/v1/demo/seed").status_code == 401


def test_register_helper_isolated_sessions():
    a = register(make_client(), "a@example.com")
    b = register(make_client(), "b@example.com")
    assert a.get("/api/v1/auth/me").json()["email"] == "a@example.com"
    assert b.get("/api/v1/auth/me").json()["email"] == "b@example.com"
