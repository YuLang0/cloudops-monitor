"""데모 모드: 가상 서버의 측정값을 만들어 낸다.

- 가상 서버는 servers.is_demo = true 로 저장되고 화면에 항상 '데모' 배지가 붙는다.
- 가상 데이터도 실제 Agent 데이터와 '같은' 저장·장애 감지 경로를 탄다(record_sample → evaluate_sample).
- 시뮬레이터가 꺼지면(CLOUDOPS_DEMO_MODE=false) 가상 서버도 다른 서버와 똑같이 '연결 끊김'이 된다.
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Server
from .alerts import evaluate_sample
from .metrics import record_sample

GIB = 1024**3

# (이름, 호스트, OS, 프로파일, 설명, RAM GiB, 디스크 GiB)
DEMO_SERVERS = [
    ("demo-web-01", "10.0.1.11", "Ubuntu 24.04 LTS", "web", "가상 웹 서버 (안정적인 부하)", 8, 80),
    ("demo-db-01", "10.0.2.21", "Rocky Linux 9", "db", "가상 DB 서버 (RAM 사용률 높음)", 32, 500),
    ("demo-batch-01", "10.0.3.31", "Debian 12", "batch", "가상 배치 서버 (주기적 CPU 급증)", 16, 200),
    ("demo-edge-01", "10.0.4.41", "Amazon Linux 2023", "flaky", "가상 엣지 서버 (주기적으로 연결 끊김)", 4, 40),
]
_SPECS = {profile: (ram, disk) for _, _, _, profile, _, ram, disk in DEMO_SERVERS}

# 프로세스 재시작 시 누적 네트워크 카운터는 0 부터 다시 센다(실제 서버 재부팅과 같은 동작)
_net_totals: dict[int, list[float]] = {}


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def generate_sample(profile: str, t: float, rng: random.Random) -> dict | None:
    """시각 t(epoch 초)의 가상 측정값. None 이면 '이 시점에는 전송하지 않음'(연결 끊김 재현)."""
    wave = math.sin(t / 97.0)
    slow = math.sin(t / 613.0)
    noise = rng.uniform(-1.0, 1.0)

    if profile == "web":
        cpu = 34 + 14 * wave + 6 * noise
        mem = 52 + 5 * slow + 1.5 * noise
        disk = 41.0
        net = 900_000 * (1.2 + wave)
    elif profile == "db":
        cpu = 42 + 12 * wave + 5 * noise
        mem = 79 + 6 * slow + 1.5 * noise  # 경고 기준(80%)을 넘나든다
        disk = 72.5
        net = 350_000 * (1.2 + slow)
    elif profile == "batch":
        in_job = (t % 420) < 75  # 7분마다 75초 동안 배치 작업
        cpu = (97.5 + 2 * noise) if in_job else (16 + 6 * wave + 4 * noise)
        mem = (71 if in_job else 44) + 2 * noise
        disk = 58.0
        net = 120_000 * (1.2 + wave) * (4 if in_job else 1)
    elif profile == "flaky":
        if (t % 300) >= 225:  # 5분마다 75초 동안 침묵
            return None
        cpu = 22 + 8 * wave + 5 * noise
        mem = 61 + 4 * slow + 2 * noise
        disk = 87.0  # 디스크 경고 기준(85%) 초과 상태
        net = 60_000 * (1.2 + slow)
    else:
        raise ValueError(f"unknown demo profile: {profile}")

    ram_gib, disk_gib = _SPECS[profile]
    cpu, mem = _clamp(cpu), _clamp(mem)
    return {
        "cpu_percent": round(cpu, 1),
        "mem_percent": round(mem, 1),
        "mem_total": ram_gib * GIB,
        "mem_used": int(ram_gib * GIB * mem / 100),
        "disk_percent": disk,
        "disk_total": disk_gib * GIB,
        "disk_used": int(disk_gib * GIB * disk / 100),
        "net_sent_rate": round(max(0.0, net * (1 + 0.2 * noise)), 1),
        "net_recv_rate": round(max(0.0, net * 0.6 * (1 - 0.2 * noise)), 1),
    }


def _with_counters(server: Server, sample: dict, now: datetime, elapsed: float) -> dict:
    totals = _net_totals.setdefault(server.id, [0.0, 0.0])
    totals[0] += sample["net_sent_rate"] * elapsed
    totals[1] += sample["net_recv_rate"] * elapsed
    return {
        **sample,
        "net_sent_total": int(totals[0]),
        "net_recv_total": int(totals[1]),
        "uptime_seconds": max(0, int((now - server.created_at).total_seconds())),
    }


def seed_demo_servers(db: Session, owner_id: int, now: datetime, backfill_minutes: int = 30) -> list[Server]:
    """사용자에게 가상 서버를 만들어 주고, 그래프가 비어 보이지 않도록 과거 구간을 채운다."""
    rng = random.Random()
    step = 10
    created = []
    for name, host, os_name, profile, description, _, _ in DEMO_SERVERS:
        server = Server(
            owner_id=owner_id, name=name, host=host, os_name=os_name, description=description,
            is_demo=True, demo_profile=profile,
            created_at=now - timedelta(minutes=backfill_minutes),
        )
        db.add(server)
        db.flush()
        t = now - timedelta(minutes=backfill_minutes)
        while t < now:
            sample = generate_sample(profile, t.timestamp(), rng)
            if sample is not None:
                record_sample(db, server, _with_counters(server, sample, t, step), t)
            t += timedelta(seconds=step)
        created.append(server)
    db.commit()
    return created


def tick(db: Session, now: datetime, elapsed: float) -> int:
    """모든 가상 서버에 대해 측정값 1건씩 생성. 생성 건수를 반환한다."""
    rng = random.Random()
    servers = db.scalars(select(Server).where(Server.is_demo.is_(True))).all()
    count = 0
    for server in servers:
        sample = generate_sample(server.demo_profile or "web", now.timestamp(), rng)
        if sample is None:
            continue
        metric = record_sample(db, server, _with_counters(server, sample, now, elapsed), now)
        evaluate_sample(db, server, metric, now)
        count += 1
    db.commit()
    return count
