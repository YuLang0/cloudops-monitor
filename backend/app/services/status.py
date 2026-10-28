"""서버 상태 계산.

상태는 DB 에 저장하지 않고 조회 시점에 계산한다. 그래야 Agent 가 조용히 죽었을 때
"마지막으로 저장된 정상 상태"가 계속 표시되는 사고를 막을 수 있다.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from ..config import get_settings
from ..models import Incident, Server


def is_stale(server: Server, now: datetime) -> bool:
    if server.last_seen_at is None:
        return True
    return now - server.last_seen_at > timedelta(seconds=get_settings().offline_after_seconds)


def compute_status(server: Server, open_incidents: list[Incident], now: datetime) -> str:
    if server.last_seen_at is None:
        return "pending"  # 한 번도 데이터를 받은 적 없음 → 정상으로 표시하지 않는다
    if is_stale(server, now):
        return "offline"
    severities = {i.severity for i in open_incidents if i.metric != "offline"}
    if "critical" in severities:
        return "critical"
    if "warning" in severities:
        return "warning"
    return "ok"
