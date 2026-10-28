from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import init_db
from .routers import auth, incidents, misc, servers
from .services.background import start_background_tasks, stop_background_tasks
from .services.locking import SingleInstanceLock

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    lock = SingleInstanceLock(get_settings().background_lock_file)
    tasks = start_background_tasks(lock)
    yield
    stop_background_tasks(tasks, lock)


_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def origin_allowed(origin: str, host: str | None, allowed: list[str]) -> bool:
    """쓰기 요청을 보낸 페이지의 출처(Origin)가 이 서비스 자신이거나 허용 목록에 있는지."""
    if origin in allowed:
        return True
    netloc = urlsplit(origin).netloc
    return bool(netloc) and host is not None and netloc.lower() == host.lower()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="CloudOps Monitor API",
        version="1.0.0",
        lifespan=lifespan,
        # 운영 환경에서는 API 문서를 외부에 노출하지 않는다
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    if settings.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origin_list,  # 와일드카드(*) 금지: 쿠키 인증과 함께 쓸 수 없다
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "DELETE"],
            allow_headers=["Content-Type", "Authorization"],
        )

    @app.middleware("http")
    async def check_origin(request: Request, call_next):
        # 쿠키 인증 + SameSite=Lax 에 더해, 다른 사이트의 페이지가 브라우저를 이용해 보낸
        # 쓰기 요청을 Origin 헤더로 한 번 더 막는다(CSRF 방어). 브라우저가 아닌 Agent 는
        # Origin 헤더를 보내지 않으므로 영향이 없다.
        origin = request.headers.get("origin")
        if (
            origin is not None
            and request.method in _UNSAFE_METHODS
            and request.url.path.startswith("/api/")
            and not origin_allowed(origin, request.headers.get("host"), settings.cors_origin_list)
        ):
            return JSONResponse(status_code=403, content={"detail": "허용되지 않은 출처의 요청입니다"})
        return await call_next(request)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # 기본 422 응답은 사용자가 보낸 값(input)을 그대로 되돌려 준다. 비밀번호 같은 값이
        # 응답·프록시 로그에 남지 않도록 위치와 메시지만 돌려준다.
        detail = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")} for e in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": detail})

    for router in (auth.router, servers.router, incidents.router, misc.router):
        app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
