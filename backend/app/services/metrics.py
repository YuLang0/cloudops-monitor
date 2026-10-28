from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import Incident, Metric, Server

# 범위 → (조회 구간 초, 버킷 초). 버킷 0 은 원본 샘플 그대로.
RANGES: dict[str, tuple[int, int]] = {
    "1m": (60, 0),
    "5m": (300, 0),
    "1h": (3600, 30),
    "24h": (86400, 300),
}

_AVG_FIELDS = ("cpu_percent", "mem_percent", "disk_percent", "net_sent_rate", "net_recv_rate")
_LAST_FIELDS = (
    "mem_used", "mem_total", "disk_used", "disk_total",
    "net_sent_total", "net_recv_total", "uptime_seconds",
)
METRIC_FIELDS = _AVG_FIELDS + _LAST_FIELDS


def record_sample(db: Session, server: Server, values: dict, now: datetime) -> Metric:
    sample = Metric(server_id=server.id, ts=now, **values)
    db.add(sample)
    server.last_seen_at = now
    return sample


def latest_metric(db: Session, server_id: int) -> Metric | None:
    return db.scalars(
        select(Metric).where(Metric.server_id == server_id).order_by(Metric.ts.desc()).limit(1)
    ).first()


def _bucket_start(ts: datetime, bucket: int) -> datetime:
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % bucket, tz=timezone.utc)


def query_series(
    db: Session, server_id: int, range_key: str, now: datetime
) -> tuple[int, datetime, list[dict]]:
    """범위에 맞는 시계열을 반환한다. 긴 범위는 버킷 평균으로 다운샘플링한다.

    집계를 SQL 이 아닌 Python 에서 하는 이유: SQLite/PostgreSQL 어느 쪽에서도 동일하게 동작시키기 위함.
    """
    seconds, bucket = RANGES[range_key]
    start = now - timedelta(seconds=seconds)
    rows = db.scalars(
        select(Metric).where(Metric.server_id == server_id, Metric.ts >= start).order_by(Metric.ts)
    ).all()

    if bucket == 0:
        return bucket, start, [{"ts": r.ts, **{f: getattr(r, f) for f in METRIC_FIELDS}} for r in rows]

    groups: dict[datetime, list[Metric]] = {}
    for r in rows:
        groups.setdefault(_bucket_start(r.ts, bucket), []).append(r)
    points = []
    for ts, items in groups.items():  # rows 가 정렬되어 있으므로 삽입 순서 = 시간 순서
        point: dict = {"ts": ts}
        for f in _AVG_FIELDS:
            point[f] = round(sum(getattr(i, f) for i in items) / len(items), 2)
        for f in _LAST_FIELDS:
            point[f] = getattr(items[-1], f)
        points.append(point)
    return bucket, start, points


def query_fleet_series(
    db: Session, server_ids: list[int], range_key: str, now: datetime
) -> tuple[int, datetime, list[dict]]:
    """여러 서버의 평균 CPU/RAM 추이. 버킷마다 '서버별 평균'을 먼저 구한 뒤 서버 간 평균을 낸다."""
    seconds, bucket = RANGES[range_key]
    bucket = bucket or 5
    start = now - timedelta(seconds=seconds)
    if not server_ids:
        return bucket, start, []
    rows = db.execute(
        select(Metric.server_id, Metric.ts, Metric.cpu_percent, Metric.mem_percent)
        .where(Metric.server_id.in_(server_ids), Metric.ts >= start)
        .order_by(Metric.ts)
    ).all()

    groups: dict[datetime, dict[int, list[tuple[float, float]]]] = {}
    for server_id, ts, cpu, mem in rows:
        groups.setdefault(_bucket_start(ts, bucket), {}).setdefault(server_id, []).append((cpu, mem))
    points = []
    for ts, per_server in groups.items():
        cpus = [sum(v[0] for v in vals) / len(vals) for vals in per_server.values()]
        mems = [sum(v[1] for v in vals) / len(vals) for vals in per_server.values()]
        points.append(
            {
                "ts": ts,
                "avg_cpu": round(sum(cpus) / len(cpus), 2),
                "avg_mem": round(sum(mems) / len(mems), 2),
                "servers": len(per_server),
            }
        )
    return bucket, start, points


def purge_old_metrics(db: Session, now: datetime, retention_days: int) -> int:
    result = db.execute(delete(Metric).where(Metric.ts < now - timedelta(days=retention_days)))
    db.commit()
    return result.rowcount or 0


def purge_old_incidents(db: Session, now: datetime, retention_days: int) -> int:
    """해결된 지 오래된 장애 이력만 지운다. 진행 중인 장애는 기간과 상관없이 남긴다."""
    result = db.execute(
        delete(Incident).where(
            Incident.resolved_at.is_not(None),
            Incident.resolved_at < now - timedelta(days=retention_days),
        )
    )
    db.commit()
    return result.rowcount or 0
