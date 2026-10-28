from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .database import get_db
from .models import Server, User
from .security import AGENT_KEY_PREFIX, COOKIE_NAME, decode_access_token, hash_agent_key

DbDep = Annotated[Session, Depends(get_db)]


def get_current_user(
    db: DbDep,
    session_cookie: Annotated[str | None, Cookie(alias=COOKIE_NAME)] = None,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    """httpOnly 쿠키(브라우저) 또는 Authorization: Bearer(API 클라이언트)로 사용자 인증."""
    token = session_cookie
    if token is None and authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    user_id = decode_access_token(token) if token else None
    user = db.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    return user


UserDep = Annotated[User, Depends(get_current_user)]


def get_owned_server(server_id: int, db: DbDep, user: UserDep) -> Server:
    """본인 소유 서버만 반환. 남의 서버는 존재 여부도 알려주지 않도록 403 이 아닌 404 로 응답한다."""
    server = db.get(Server, server_id)
    if server is None or server.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "서버를 찾을 수 없습니다")
    return server


OwnedServerDep = Annotated[Server, Depends(get_owned_server)]


def get_agent_server(db: DbDep, authorization: Annotated[str | None, Header()] = None) -> Server:
    """Agent 인증키로 서버를 식별한다. 키 1개 = 서버 1대이므로 다른 서버의 데이터를 쓸 수 없다."""
    invalid = HTTPException(status.HTTP_401_UNAUTHORIZED, "유효하지 않은 Agent 인증키입니다")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise invalid
    key = authorization[7:].strip()
    if not key.startswith(AGENT_KEY_PREFIX) or len(key) > 128:
        raise invalid
    server = db.scalars(select(Server).where(Server.agent_key_hash == hash_agent_key(key))).first()
    if server is None or server.is_demo:
        raise invalid
    return server


AgentServerDep = Annotated[Server, Depends(get_agent_server)]
