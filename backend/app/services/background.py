"""백그라운드 작업: 데모 시뮬레이터, 연결 끊김 감시, 오래된 데이터 정리."""
from __future__ import annotations

import asyncio
import logging

from ..config import get_settings
from ..database import SessionLocal, utcnow
from . import alerts, demo, metrics
from .locking import SingleInstanceLock

logger = logging.getLogger("cloudops")

# 이 프로세스가 백그라운드 작업을 맡고 있는지. /health 에서 보여 준다.
#   running  : 이 프로세스가 실행 중
#   standby  : 다른 프로세스가 잠금을 가지고 있어 API 만 처리
#   stopped  : 아직 시작 전이거나 종료됨
state = {"background": "stopped"}


def _run(fn, *args):
    with SessionLocal() as db:
        return fn(db, *args)


async def _loop(name: str, interval: float, job, initial_delay: float = 0.0) -> None:
    await asyncio.sleep(initial_delay)
    while True:
        try:
            await asyncio.to_thread(job)
        except Exception:  # 한 번 실패해도 루프는 계속 돈다
            logger.exception("백그라운드 작업 실패: %s", name)
        await asyncio.sleep(interval)


def _retention() -> None:
    settings = get_settings()
    now = utcnow()
    removed_metrics = _run(metrics.purge_old_metrics, now, settings.retention_days)
    removed_incidents = _run(metrics.purge_old_incidents, now, settings.incident_retention_days)
    if removed_metrics or removed_incidents:
        logger.info("보존 기간 정리: 측정값 %d건, 해결된 장애 %d건 삭제", removed_metrics, removed_incidents)


def start_background_tasks(lock: SingleInstanceLock) -> list[asyncio.Task]:
    settings = get_settings()
    if not lock.acquire():
        state["background"] = "standby"
        logger.warning(
            "다른 프로세스가 백그라운드 작업을 실행 중입니다(잠금: %s). 이 프로세스는 API 요청만 처리합니다.",
            lock.path,
        )
        return []
    state["background"] = "running"
    tasks = [
        # 백엔드가 막 재시작된 직후에는 Agent 들이 다시 보고할 시간을 준 뒤 감시를 시작한다
        asyncio.create_task(
            _loop(
                "offline-watch", 5.0, lambda: _run(alerts.detect_offline, utcnow()),
                initial_delay=settings.offline_after_seconds,
            )
        ),
        asyncio.create_task(_loop("retention", 3600.0, _retention)),
    ]
    if settings.demo_mode:
        interval = settings.demo_interval_seconds
        tasks.append(
            asyncio.create_task(_loop("demo", interval, lambda: _run(demo.tick, utcnow(), interval)))
        )
        logger.info("데모 모드 활성화: 가상 서버 측정값을 %.0f초마다 생성합니다", interval)
    return tasks


def stop_background_tasks(tasks: list[asyncio.Task], lock: SingleInstanceLock) -> None:
    for task in tasks:
        task.cancel()
    lock.release()
    state["background"] = "stopped"
