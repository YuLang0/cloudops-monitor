#!/usr/bin/env python3
"""CloudOps Monitor Agent

이 서버의 CPU / RAM / 디스크 / 네트워크 / 가동 시간을 psutil 로 측정해
CloudOps Monitor 백엔드로 주기적으로 전송(push)한다.

보안 설계
- 읽기 전용: 측정값을 읽어서 보내기만 한다. 백엔드로부터 명령을 받아 실행하는 기능이 없다.
- 포트를 열지 않는다: Agent 는 밖으로 나가는(outbound) HTTPS 요청만 한다.
- 인증키는 환경변수로만 받는다(명령행 인자는 `ps` 로 다른 사용자에게 노출될 수 있다).
- localhost 가 아닌 주소에 http:// 로 보내려 하면 실행을 거부한다(키가 평문으로 새는 것을 방지).

반드시 본인이 소유했거나 모니터링 허가를 받은 서버에서만 실행하세요.

사용법
    export CLOUDOPS_URL=https://monitor.example.com
    export CLOUDOPS_AGENT_KEY=cops_xxxxxxxx
    python agent.py
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import signal
import socket
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

import psutil

AGENT_VERSION = "1.0.0"
MIN_INTERVAL = 2.0
MAX_BACKOFF = 60.0
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

log = logging.getLogger("cloudops-agent")


class FatalError(Exception):
    """재시도해도 소용없는 오류(잘못된 설정, 거부된 인증키 등)."""


def os_description() -> str:
    if sys.platform.startswith("linux"):
        try:
            info = platform.freedesktop_os_release()
            return info.get("PRETTY_NAME") or f"Linux {platform.release()}"
        except OSError:
            pass
    if sys.platform == "darwin":
        return f"macOS {platform.mac_ver()[0]}"
    return f"{platform.system()} {platform.release()}"


def default_disk_path() -> str:
    if os.name == "nt":
        return os.environ.get("SystemDrive", "C:") + "\\"
    return "/"


class Collector:
    """측정값 수집기. 네트워크 속도는 직전 측정과의 누적 카운터 차이로 계산한다."""

    def __init__(self, disk_path: str) -> None:
        self.disk_path = disk_path
        self.hostname = socket.gethostname()
        self.os = os_description()
        psutil.cpu_percent(interval=None)  # 첫 호출은 기준점만 잡는다(의미 없는 0.0 반환)
        self._last_net = psutil.net_io_counters()
        self._last_time = time.monotonic()

    def collect(self) -> dict:
        now = time.monotonic()
        elapsed = max(now - self._last_time, 1e-6)
        net = psutil.net_io_counters()
        # 카운터가 초기화(재부팅·인터페이스 재시작)되면 음수가 나올 수 있으므로 0 으로 막는다
        sent_rate = max(0.0, (net.bytes_sent - self._last_net.bytes_sent) / elapsed)
        recv_rate = max(0.0, (net.bytes_recv - self._last_net.bytes_recv) / elapsed)
        self._last_net, self._last_time = net, now

        mem = psutil.virtual_memory()
        disk = psutil.disk_usage(self.disk_path)
        return {
            "cpu_percent": round(psutil.cpu_percent(interval=None), 1),  # 직전 호출 이후 구간의 평균
            "mem_percent": round(mem.percent, 1),
            "mem_used": int(mem.total - mem.available),
            "mem_total": int(mem.total),
            "disk_percent": round(disk.percent, 1),
            "disk_used": int(disk.used),
            "disk_total": int(disk.total),
            "net_sent_rate": round(sent_rate, 1),
            "net_recv_rate": round(recv_rate, 1),
            "net_sent_total": int(net.bytes_sent),
            "net_recv_total": int(net.bytes_recv),
            "uptime_seconds": int(time.time() - psutil.boot_time()),
            "hostname": self.hostname[:253],
            "os": self.os[:128],
            "agent_version": AGENT_VERSION,
        }


def validate_url(base_url: str, allow_insecure: bool) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise FatalError(f"CLOUDOPS_URL 형식이 올바르지 않습니다: {base_url!r}")
    if parsed.scheme == "http" and parsed.hostname not in _LOCAL_HOSTS and not allow_insecure:
        raise FatalError(
            "localhost 가 아닌 주소에는 https:// 를 사용해야 합니다. "
            "(신뢰할 수 있는 사설망에서만 CLOUDOPS_ALLOW_INSECURE=1 로 해제 가능)"
        )
    return base_url.rstrip("/") + "/api/v1/ingest"


def send(endpoint: str, agent_key: str, payload: dict, timeout: float = 10.0) -> None:
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {agent_key}",
            "User-Agent": f"cloudops-agent/{AGENT_VERSION}",
        },
    )
    try:
        # urllib 은 기본적으로 TLS 인증서를 검증한다. 검증을 끄는 옵션은 일부러 제공하지 않는다.
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise FatalError("인증키가 거부되었습니다. CLOUDOPS_AGENT_KEY 를 확인하세요(키를 재발급했나요?)")
        if exc.code == 422:
            raise FatalError(f"백엔드가 측정값 형식을 거부했습니다(Agent/백엔드 버전 불일치?): {exc.read()[:300]!r}")
        raise ConnectionError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ConnectionError(str(getattr(exc, "reason", exc))) from exc


def run(endpoint: str, agent_key: str, interval: float, disk_path: str, once: bool) -> int:
    collector = Collector(disk_path)
    log.info("시작: host=%s os=%s 주기=%.0fs → %s", collector.hostname, collector.os, interval, endpoint)

    stopping = False

    def _stop(*_):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    time.sleep(1.0)  # CPU·네트워크 속도 계산에 필요한 최소 구간 확보
    failures = 0
    while not stopping:
        started = time.monotonic()
        payload = collector.collect()
        try:
            send(endpoint, agent_key, payload)
            if failures:
                log.info("연결 복구됨")
            failures = 0
            log.debug("전송 완료: cpu=%.1f%% mem=%.1f%% disk=%.1f%%",
                      payload["cpu_percent"], payload["mem_percent"], payload["disk_percent"])
        except ConnectionError as exc:
            failures += 1
            log.warning("전송 실패(%d회 연속): %s", failures, exc)
        if once:
            return 0 if failures == 0 else 1

        # 실패가 이어지면 대기 시간을 늘려(지수 백오프) 죽어 있는 백엔드를 두드리지 않는다
        delay = interval if failures == 0 else min(MAX_BACKOFF, interval * 2 ** min(failures, 5))
        deadline = started + delay
        while not stopping and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))
    log.info("종료")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="CloudOps Monitor Agent")
    parser.add_argument("--url", default=os.environ.get("CLOUDOPS_URL", ""), help="백엔드 주소 (환경변수 CLOUDOPS_URL)")
    parser.add_argument("--interval", type=float, default=float(os.environ.get("CLOUDOPS_INTERVAL", "5")),
                        help="전송 주기(초). 기본 5")
    parser.add_argument("--disk-path", default=os.environ.get("CLOUDOPS_DISK_PATH", default_disk_path()),
                        help="사용률을 측정할 디스크 경로")
    parser.add_argument("--once", action="store_true", help="한 번만 전송하고 종료(연결 테스트용)")
    parser.add_argument("--print", action="store_true", dest="print_only", help="전송하지 않고 측정값만 출력")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        if args.print_only:
            collector = Collector(args.disk_path)
            time.sleep(1.0)
            print(json.dumps(collector.collect(), indent=2, ensure_ascii=False))
            return 0

        agent_key = os.environ.get("CLOUDOPS_AGENT_KEY", "").strip()
        if not args.url:
            raise FatalError("CLOUDOPS_URL 환경변수(또는 --url)가 필요합니다")
        if not agent_key:
            raise FatalError("CLOUDOPS_AGENT_KEY 환경변수가 필요합니다")
        endpoint = validate_url(args.url, os.environ.get("CLOUDOPS_ALLOW_INSECURE") == "1")
        return run(endpoint, agent_key, max(MIN_INTERVAL, args.interval), args.disk_path, args.once)
    except FatalError as exc:
        log.error("%s", exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
