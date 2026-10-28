from __future__ import annotations

import csv
import io
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import DbDep, UserDep
from ..models import Incident, Server
from ..schemas import IncidentOut

router = APIRouter(prefix="/incidents", tags=["incidents"])

StateFilter = Literal["all", "open", "resolved"]


def query_incidents(
    db: Session, owner_id: int, state: str = "all", server_id: int | None = None, limit: int = 100
) -> list[IncidentOut]:
    # 반드시 servers 와 조인해 owner_id 로 걸러낸다 → 다른 사용자의 장애 이력은 조회 불가
    stmt = (
        select(Incident, Server.name, Server.is_demo)
        .join(Server, Incident.server_id == Server.id)
        .where(Server.owner_id == owner_id)
        .order_by(Incident.started_at.desc(), Incident.id.desc())
        .limit(limit)
    )
    if state == "open":
        stmt = stmt.where(Incident.resolved_at.is_(None))
    elif state == "resolved":
        stmt = stmt.where(Incident.resolved_at.is_not(None))
    if server_id is not None:
        stmt = stmt.where(Incident.server_id == server_id)
    return [
        IncidentOut(
            id=i.id, server_id=i.server_id, server_name=name, is_demo=is_demo, metric=i.metric,
            severity=i.severity, started_at=i.started_at, resolved_at=i.resolved_at,
            threshold=i.threshold, peak_value=i.peak_value, last_value=i.last_value, message=i.message,
        )
        for i, name, is_demo in db.execute(stmt).all()
    ]


@router.get("", response_model=list[IncidentOut])
def list_incidents(
    db: DbDep,
    user: UserDep,
    state: StateFilter = "all",
    server_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    return query_incidents(db, user.id, state, server_id, limit)


def _csv_safe(value: str) -> str:
    """CSV 수식 삽입(=, +, -, @ 로 시작하는 셀) 방지."""
    return "'" + value if value[:1] in ("=", "+", "-", "@", "\t", "\r") else value


@router.get("/export")
def export_incidents_csv(db: DbDep, user: UserDep, state: StateFilter = "all", server_id: int | None = None):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        ["id", "server", "data_source", "metric", "severity", "started_at_utc", "resolved_at_utc",
         "threshold", "peak_value", "message"]
    )
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    for i in query_incidents(db, user.id, state, server_id, limit=5000):
        writer.writerow(
            [
                i.id, _csv_safe(i.server_name), "demo" if i.is_demo else "agent", i.metric, i.severity,
                i.started_at.strftime(fmt), i.resolved_at.strftime(fmt) if i.resolved_at else "",
                "" if i.threshold is None else i.threshold,
                "" if i.peak_value is None else i.peak_value,
                _csv_safe(i.message),
            ]
        )
    return Response(
        "﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="incidents.csv"'},
    )
