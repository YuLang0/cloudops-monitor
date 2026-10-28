"""대시보드, Agent 수집, 데모, 헬스체크 라우터."""
from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select, text

from ..config import get_settings
from ..database import utcnow
from ..deps import AgentServerDep, DbDep, UserDep
from ..models import Server
from ..schemas import DashboardSummary, FleetSeries, IngestPayload, PublicConfig, ServerOut
from ..services import background, demo
from ..services.alerts import evaluate_sample
from ..services.metrics import query_fleet_series, record_sample
from .incidents import query_incidents
from .servers import RangeQuery, list_server_outs

router = APIRouter()


# ---------- 공개 ----------
@router.get("/health", tags=["system"])
def health(db: DbDep):
    """상태 확인. 컨테이너 헬스체크·상태 스크립트가 사용한다(로그인 불필요, 비밀정보 없음).

    DB 에 실제로 질의해 보고 실패하면 503 을 돌려준다. 그래야 "프로세스는 살아 있지만
    DB 를 못 읽는" 상태를 정상으로 착각하지 않는다.
    """
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(status_code=503, content={"status": "error", "database": "error"})
    return {"status": "ok", "database": "ok", "background": background.state["background"]}


@router.get("/config", response_model=PublicConfig, tags=["system"])
def public_config():
    s = get_settings()
    return PublicConfig(
        demo_mode=s.demo_mode,
        allow_registration=s.allow_registration,
        offline_after_seconds=s.offline_after_seconds,
    )


# ---------- 대시보드 ----------
@router.get("/dashboard/summary", response_model=DashboardSummary, tags=["dashboard"])
def dashboard_summary(db: DbDep, user: UserDep):
    servers = list_server_outs(db, user.id, utcnow())
    counts = {k: 0 for k in ("ok", "warning", "critical", "offline", "pending")}
    for s in servers:
        counts[s.status] += 1
    # 평균은 '지금 데이터를 보내고 있는' 서버만 대상으로 한다. 끊긴 서버의 옛 값을 섞지 않는다.
    live = [s.latest for s in servers if s.status in ("ok", "warning", "critical") and s.latest]
    return DashboardSummary(
        total=len(servers),
        demo=sum(1 for s in servers if s.is_demo),
        avg_cpu=round(sum(m.cpu_percent for m in live) / len(live), 1) if live else None,
        avg_mem=round(sum(m.mem_percent for m in live) / len(live), 1) if live else None,
        reporting=len(live),
        open_incidents=sum(s.open_incident_count for s in servers),
        recent_incidents=query_incidents(db, user.id, limit=8),
        **counts,
    )


@router.get("/dashboard/timeseries", response_model=FleetSeries, tags=["dashboard"])
def dashboard_timeseries(db: DbDep, user: UserDep, range_key: RangeQuery = "5m"):
    now = utcnow()
    ids = list(db.scalars(select(Server.id).where(Server.owner_id == user.id)).all())
    bucket, start, points = query_fleet_series(db, ids, range_key, now)
    return FleetSeries(range=range_key, bucket_seconds=bucket, start=start, end=now, points=points)


# ---------- Agent 수집 ----------
@router.post("/ingest", status_code=status.HTTP_202_ACCEPTED, tags=["agent"])
def ingest(body: IngestPayload, server: AgentServerDep, db: DbDep):
    """Agent 가 측정값을 밀어 넣는(push) 유일한 통로.

    백엔드는 등록된 서버 주소로 '접속하지 않는다'. 따라서 사용자가 입력한 주소로
    내부망을 찌르는 SSRF 가 구조적으로 불가능하다.
    """
    now = utcnow()
    min_interval = get_settings().ingest_min_interval_seconds
    if server.last_seen_at and now - server.last_seen_at < timedelta(seconds=min_interval):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "전송 주기가 너무 짧습니다")

    values = body.model_dump(exclude={"hostname", "os", "agent_version"})
    sample = record_sample(db, server, values, now)
    server.reported_hostname = body.hostname or server.reported_hostname
    server.reported_os = body.os or server.reported_os
    server.agent_version = body.agent_version or server.agent_version
    evaluate_sample(db, server, sample, now)
    db.commit()
    return {"accepted": True, "received_at": now}


# ---------- 데모 ----------
@router.post("/demo/seed", response_model=list[ServerOut], status_code=status.HTTP_201_CREATED, tags=["demo"])
def seed_demo(db: DbDep, user: UserDep):
    if not get_settings().demo_mode:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "데모 모드가 꺼져 있습니다")
    exists = db.scalars(
        select(Server.id).where(Server.owner_id == user.id, Server.is_demo.is_(True)).limit(1)
    ).first()
    if exists is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 데모 서버가 있습니다")
    now = utcnow()
    demo.seed_demo_servers(db, user.id, now)
    return [s for s in list_server_outs(db, user.id, now) if s.is_demo]


@router.delete("/demo", status_code=status.HTTP_204_NO_CONTENT, tags=["demo"])
def remove_demo(db: DbDep, user: UserDep):
    # DB 의 ON DELETE CASCADE 로 측정값·장애 이력도 함께 삭제된다
    db.execute(delete(Server).where(Server.owner_id == user.id, Server.is_demo.is_(True)))
    db.commit()
