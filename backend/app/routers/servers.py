from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import utcnow
from ..deps import DbDep, OwnedServerDep, UserDep
from ..models import Incident, Server
from ..schemas import MetricPoint, MetricSeries, RangeKey, ServerCreate, ServerCreated, ServerOut, ServerUpdate
from ..security import generate_agent_key
from ..services.metrics import METRIC_FIELDS, latest_metric, query_series
from ..services.status import compute_status

router = APIRouter(prefix="/servers", tags=["servers"])

_THRESHOLD_FIELDS = ("cpu_warn", "cpu_crit", "mem_warn", "mem_crit", "disk_warn", "disk_crit")


def open_incidents_by_server(db: Session, server_ids: list[int]) -> dict[int, list[Incident]]:
    result: dict[int, list[Incident]] = {sid: [] for sid in server_ids}
    if server_ids:
        rows = db.scalars(
            select(Incident).where(Incident.server_id.in_(server_ids), Incident.resolved_at.is_(None))
        ).all()
        for incident in rows:
            result[incident.server_id].append(incident)
    return result


def to_server_out(db: Session, server: Server, open_incidents: list[Incident], now: datetime) -> ServerOut:
    latest = latest_metric(db, server.id)
    status_value = compute_status(server, open_incidents, now)
    # 연결이 끊긴 동안에는 임계치 장애가 아니라 '연결 끊김' 자체가 문제이므로 그것만 센다
    counted = [i for i in open_incidents if (i.metric == "offline") == (status_value == "offline")]
    return ServerOut(
        id=server.id,
        name=server.name,
        host=server.host,
        os_name=server.os_name,
        description=server.description,
        is_demo=server.is_demo,
        status=status_value,
        last_seen_at=server.last_seen_at,
        reported_hostname=server.reported_hostname,
        reported_os=server.reported_os,
        agent_version=server.agent_version,
        agent_key_prefix=server.agent_key_prefix,
        open_incident_count=len(counted),
        latest=MetricPoint.model_validate(latest) if latest else None,
        created_at=server.created_at,
        **{f: getattr(server, f) for f in _THRESHOLD_FIELDS},
    )


def list_server_outs(db: Session, owner_id: int, now: datetime) -> list[ServerOut]:
    servers = db.scalars(select(Server).where(Server.owner_id == owner_id).order_by(Server.name)).all()
    incidents = open_incidents_by_server(db, [s.id for s in servers])
    return [to_server_out(db, s, incidents[s.id], now) for s in servers]


@router.get("", response_model=list[ServerOut])
def list_servers(db: DbDep, user: UserDep):
    return list_server_outs(db, user.id, utcnow())


@router.post("", response_model=ServerCreated, status_code=status.HTTP_201_CREATED)
def create_server(body: ServerCreate, db: DbDep, user: UserDep):
    key, key_hash, prefix = generate_agent_key()
    server = Server(owner_id=user.id, agent_key_hash=key_hash, agent_key_prefix=prefix, **body.model_dump())
    db.add(server)
    db.commit()
    return ServerCreated(server=to_server_out(db, server, [], utcnow()), agent_key=key)


@router.get("/{server_id}", response_model=ServerOut)
def get_server(server: OwnedServerDep, db: DbDep):
    incidents = open_incidents_by_server(db, [server.id])[server.id]
    return to_server_out(db, server, incidents, utcnow())


@router.put("/{server_id}", response_model=ServerOut)
def update_server(body: ServerUpdate, server: OwnedServerDep, db: DbDep):
    for field, value in body.model_dump().items():
        setattr(server, field, value)
    db.commit()
    incidents = open_incidents_by_server(db, [server.id])[server.id]
    return to_server_out(db, server, incidents, utcnow())


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_server(server: OwnedServerDep, db: DbDep):
    db.delete(server)
    db.commit()


@router.post("/{server_id}/rotate-key", response_model=ServerCreated)
def rotate_agent_key(server: OwnedServerDep, db: DbDep):
    """Agent 인증키 재발급. 기존 키는 즉시 무효가 된다."""
    if server.is_demo:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "데모 서버에는 Agent 인증키를 발급할 수 없습니다")
    key, server.agent_key_hash, server.agent_key_prefix = generate_agent_key()
    db.commit()
    incidents = open_incidents_by_server(db, [server.id])[server.id]
    return ServerCreated(server=to_server_out(db, server, incidents, utcnow()), agent_key=key)


RangeQuery = Annotated[RangeKey, Query(alias="range")]


@router.get("/{server_id}/metrics", response_model=MetricSeries)
def get_metrics(server: OwnedServerDep, db: DbDep, range_key: RangeQuery = "5m"):
    now = utcnow()
    bucket, start, points = query_series(db, server.id, range_key, now)
    return MetricSeries(range=range_key, bucket_seconds=bucket, start=start, end=now, points=points)


@router.get("/{server_id}/metrics/export")
def export_metrics_csv(server: OwnedServerDep, db: DbDep, range_key: RangeQuery = "24h"):
    _, _, points = query_series(db, server.id, range_key, utcnow())
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["timestamp_utc", "data_source", *METRIC_FIELDS])
    source = "demo" if server.is_demo else "agent"
    for p in points:
        writer.writerow([p["ts"].strftime("%Y-%m-%dT%H:%M:%SZ"), source, *(p[f] for f in METRIC_FIELDS)])
    filename = f"server-{server.id}-metrics-{range_key}.csv"
    return Response(
        "﻿" + buf.getvalue(),  # Excel 에서 한글이 깨지지 않도록 BOM 추가
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
