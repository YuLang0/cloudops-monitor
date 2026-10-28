"""프로세스 간 단일 실행 잠금.

연결 끊김 감시·데모 시뮬레이터·보존 기간 정리는 한 프로세스에서만 돌아야 한다.
uvicorn 워커를 늘리거나 백엔드 컨테이너를 두 개 띄우면 같은 작업이 중복 실행되어
장애가 두 번 열리거나 데모 측정값이 두 배로 쌓인다. 데이터 폴더(볼륨)에 있는 파일에
OS 잠금을 걸어, 잠금을 얻은 프로세스만 백그라운드 작업을 실행한다.

OS 잠금은 프로세스가 죽으면 커널이 자동으로 풀어 주므로, 비정상 종료 뒤에 잠금이
남아 다시 시작하지 못하는 일이 없다.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import IO

if os.name == "nt":  # 개발 PC(Windows)
    import msvcrt
else:  # 서버(Linux)
    import fcntl


class SingleInstanceLock:
    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._handle: IO[str] | None = None

    @property
    def held(self) -> bool:
        return self._handle is not None

    def acquire(self) -> bool:
        """잠금을 얻으면 True. 다른 프로세스가 이미 가지고 있으면 기다리지 않고 False."""
        if self._handle is not None:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+")
        try:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            return False
        handle.seek(0)
        handle.truncate()
        handle.write(f"{os.getpid()}\n")  # 누가 잡고 있는지 확인용(잠금 자체는 OS 가 관리)
        handle.flush()
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None
