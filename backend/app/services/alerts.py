"""임계치 기반 장애 감지.

규칙
- 측정값이 경고/장애 기준 이상이면 해당 (서버, 항목)에 장애 1건을 연다.
- 이미 열려 있는 장애가 있으면 새로 만들지 않고 최고값·심각도만 갱신한다(중복 알림 방지).
- 기준 아래로 내려온 샘플이 연속 N회(CLOUDOPS_CLEAR_SAMPLES) 이어져야 해결 처리한다(플래핑 방지).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import Incident, Metric, Server
from .status import is_stale

METRIC_LABELS = {"cpu": "CPU", "memory": "RAM", "disk": "디스크"}
_RANK = {"warning": 1, "critical": 2}


def _open_incidents(db: Session, server_id: int) -> dict[str, Incident]:
    rows = db.scalars(
        select(Incident).where(Incident.server_id == server_id, Incident.resolved_at.is_(None))
    ).all()
    return {i.metric: i for i in rows}


def evaluate_sample(db: Session, server: Server, sample: Metric, now: datetime) -> None:
    """새 측정값 1건을 기준과 비교해 장애를 열거나 갱신하거나 해결한다. commit 은 호출자가 한다."""
    open_by_metric = _open_incidents(db, server.id)

    # 데이터가 다시 들어왔으므로 연결 끊김 장애는 즉시 해결
    offline = open_by_metric.get("offline")
    if offline is not None:
        offline.resolved_at = now

    checks = (
        ("cpu", sample.cpu_percent, server.cpu_warn, server.cpu_crit),
        ("memory", sample.mem_percent, server.mem_warn, server.mem_crit),
        ("disk", sample.disk_percent, server.disk_warn, server.disk_crit),
    )
    for metric, value, warn, crit in checks:
        level = "critical" if value >= crit else "warning" if value >= warn else None
        incident = open_by_metric.get(metric)
        if level is not None:
            threshold = float(crit if level == "critical" else warn)
            if incident is None:
                db.add(
                    Incident(
                        server_id=server.id,
                        metric=metric,
                        severity=level,
                        started_at=now,
                        threshold=threshold,
                        peak_value=value,
                        last_value=value,
                        message=f"{METRIC_LABELS[metric]} 사용률 {value:.1f}% (기준 {threshold:.0f}%)",
                    )
                )
            else:
                incident.clear_streak = 0
                incident.last_value = value
                incident.peak_value = max(incident.peak_value or 0.0, value)
                if _RANK[level] > _RANK[incident.severity]:
                    incident.severity = level
                    incident.threshold = threshold
                incident.message = (
                    f"{METRIC_LABELS[metric]} 사용률 최고 {incident.peak_value:.1f}% "
                    f"(기준 {incident.threshold:.0f}%)"
                )
        elif incident is not None:
            incident.last_value = value
            incident.clear_streak += 1
            if incident.clear_streak >= get_settings().clear_samples:
                incident.resolved_at = now


def detect_offline(db: Session, now: datetime) -> int:
    """수신이 끊긴 서버에 '연결 끊김' 장애를 연다. 새로 연 건수를 반환한다."""
    already = set(
        db.scalars(
            select(Incident.server_id).where(Incident.metric == "offline", Incident.resolved_at.is_(None))
        ).all()
    )
    servers = db.scalars(select(Server).where(Server.last_seen_at.is_not(None))).all()
    opened = 0
    for server in servers:
        if server.id in already or not is_stale(server, now):
            continue
        db.add(
            Incident(
                server_id=server.id,
                metric="offline",
                severity="critical",
                started_at=now,
                message=f"{get_settings().offline_after_seconds}초 이상 데이터가 수신되지 않았습니다",
            )
        )
        opened += 1
    if opened:
        db.commit()
    return opened
