from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from .config import get_settings
from .database import utcnow

COOKIE_NAME = "cloudops_session"
AGENT_KEY_PREFIX = "cops_"
JWT_ALGORITHM = "HS256"

_hasher = PasswordHasher()  # Argon2id (OWASP 권장 알고리즘)
# 존재하지 않는 계정으로 로그인해도 같은 시간이 걸리도록 비교용 더미 해시를 준비한다(계정 존재 여부 추측 방지)
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = utcnow()
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(minutes=settings.access_token_minutes)}
    return jwt.encode(payload, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[JWT_ALGORITHM])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def generate_agent_key() -> tuple[str, str, str]:
    """(평문 키, 해시, 표시용 접두부) 반환. 평문은 생성 직후 한 번만 사용자에게 보여준다."""
    key = AGENT_KEY_PREFIX + secrets.token_urlsafe(32)
    return key, hash_agent_key(key), key[:10]


def hash_agent_key(key: str) -> str:
    # 키 자체가 256bit 난수이므로 느린 해시 없이 SHA-256 으로 충분하다
    return hashlib.sha256(key.encode()).hexdigest()


class LoginRateLimiter:
    """로그인 무차별 대입 방지용 인메모리 제한기(프로세스 1개 기준)."""

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        window = get_settings().login_window_seconds
        q = self._failures[key]
        while q and now - q[0] > window:
            q.popleft()
        return q

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            blocked = len(self._prune(key, time.monotonic())) >= get_settings().login_max_failures
            if not self._failures[key]:
                del self._failures[key]
            return blocked

    def record_failure(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._prune(key, now).append(now)

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._failures.clear()
            else:
                self._failures.pop(key, None)


login_limiter = LoginRateLimiter()
