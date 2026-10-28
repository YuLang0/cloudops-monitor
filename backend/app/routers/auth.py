from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..deps import DbDep, UserDep
from ..models import User
from ..schemas import Credentials, UserOut
from ..security import COOKIE_NAME, create_access_token, hash_password, login_limiter, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(response: Response, user_id: int) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_access_token(user_id),
        max_age=settings.access_token_minutes * 60,
        httponly=True,  # JS 에서 읽을 수 없음 → XSS 로 토큰 탈취 불가
        samesite="lax",  # 타 사이트에서 보낸 POST 에는 쿠키가 붙지 않음 → CSRF 완화
        secure=settings.cookie_secure,
        path="/",
    )


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: Credentials, response: Response, db: DbDep):
    if not get_settings().allow_registration:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "회원가입이 비활성화되어 있습니다")
    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 가입된 이메일입니다")
    _set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login(body: Credentials, request: Request, response: Response, db: DbDep):
    client_ip = request.client.host if request.client else "unknown"
    limiter_key = f"{client_ip}|{body.email}"
    if login_limiter.is_blocked(limiter_key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요"
        )
    user = db.scalars(select(User).where(User.email == body.email)).first()
    if not verify_password(body.password, user.password_hash if user else None):
        login_limiter.record_failure(limiter_key)
        # 이메일이 틀렸는지 비밀번호가 틀렸는지 구분해서 알려주지 않는다
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "이메일 또는 비밀번호가 올바르지 않습니다")
    login_limiter.reset(limiter_key)
    _set_session_cookie(response, user.id)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: UserDep):
    return user
