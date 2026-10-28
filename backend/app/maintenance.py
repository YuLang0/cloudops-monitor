"""SQLite 백업·검증·복원 도구 (배포 스크립트가 컨테이너 안에서 호출한다).

    python -m app.maintenance backup  <저장할 파일>   # 실행 중에도 일관된 백업
    python -m app.maintenance verify  <백업 파일>     # 무결성·구조 확인
    python -m app.maintenance restore <백업 파일>     # 백엔드가 멈춘 상태에서만 동작

일관성: 파일 복사(cp)는 쓰기 도중이면 깨진 파일이 나올 수 있고 WAL 파일을 빠뜨린다.
SQLite 의 온라인 백업 API(sqlite3.Connection.backup)는 한 시점의 완전한 스냅샷을 만든다.

출력에는 행 수 같은 요약만 나오고 비밀번호 해시·키 해시 같은 값은 나오지 않는다.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

from sqlalchemy.engine import make_url

from .config import get_settings
from .services.locking import SingleInstanceLock

REQUIRED_TABLES = ("users", "servers", "metrics", "incidents")


class MaintenanceError(Exception):
    pass


def database_path() -> Path:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise MaintenanceError("이 도구는 파일 SQLite 데이터베이스에서만 동작합니다")
    return Path(url.database)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise MaintenanceError(f"파일이 없습니다: {path}")
    return sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)


def verify(path: Path) -> dict[str, int]:
    """무결성 검사 + 필요한 테이블 확인. 테이블별 행 수를 돌려준다."""
    try:
        conn = _connect_readonly(path)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise MaintenanceError(f"무결성 검사 실패: {result}")
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = [t for t in REQUIRED_TABLES if t not in tables]
            if missing:
                raise MaintenanceError(f"CloudOps Monitor 데이터베이스가 아닙니다(없는 테이블: {', '.join(missing)})")
            return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in REQUIRED_TABLES}
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise MaintenanceError(f"SQLite 데이터베이스로 열 수 없습니다: {exc}") from exc


def _copy(src: sqlite3.Connection, dst_path: Path) -> None:
    dst_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst_path.with_name(dst_path.name + ".partial")
    tmp.unlink(missing_ok=True)
    dst = sqlite3.connect(tmp)
    try:
        src.backup(dst)  # 한 시점의 일관된 스냅샷
        dst.execute("PRAGMA journal_mode=DELETE")  # 백업 파일은 WAL 없이 파일 하나로 완결되게
        dst.commit()
    finally:
        dst.close()
    os.replace(tmp, dst_path)


def backup(dst_path: Path, src_path: Path | None = None) -> dict[str, int]:
    src_path = src_path or database_path()
    if dst_path.resolve() == src_path.resolve():
        raise MaintenanceError("백업 파일 경로가 원본과 같습니다")
    if dst_path.exists():
        raise MaintenanceError(f"이미 있는 파일은 덮어쓰지 않습니다: {dst_path}")
    src = _connect_readonly(src_path)
    try:
        _copy(src, dst_path)
    finally:
        src.close()
    return verify(dst_path)


def restore(backup_path: Path, db_path: Path | None = None, lock_path: Path | None = None) -> dict[str, int]:
    """백업 파일을 현재 데이터베이스 자리에 넣는다. 백엔드가 실행 중이면 거부한다."""
    db_path = db_path or database_path()
    counts = verify(backup_path)  # 깨진 파일로 덮어쓰기 전에 먼저 검사

    # 백엔드는 실행 중에 백그라운드 잠금을 쥐고 있다. 잠금을 얻을 수 있어야 '멈춘 상태'로 본다.
    lock = SingleInstanceLock(lock_path or get_settings().background_lock_file)
    if not lock.acquire():
        raise MaintenanceError("백엔드가 실행 중입니다. 먼저 백엔드를 멈춘 뒤 복원하세요")
    try:
        src = _connect_readonly(backup_path)
        staged = db_path.with_name(db_path.name + ".restoring")
        try:
            staged.unlink(missing_ok=True)
            _copy(src, staged)
        finally:
            src.close()
        verify(staged)
        # 이전 DB 의 WAL/SHM 이 남아 있으면 새 파일에 잘못 적용될 수 있으므로 지운다
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        os.replace(staged, db_path)
    finally:
        lock.release()
    return counts


def _summary(counts: dict[str, int]) -> str:
    return ", ".join(f"{t} {n}" for t, n in counts.items())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.maintenance", description="CloudOps Monitor SQLite 백업 도구")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "verify", "restore"):
        sub.add_parser(name).add_argument("path", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "backup":
            counts = backup(args.path)
            print(f"백업 완료: {args.path} ({_summary(counts)})")
        elif args.command == "verify":
            print(f"검증 통과: {_summary(verify(args.path))}")
        else:
            counts = restore(args.path)
            print(f"복원 완료: {_summary(counts)}")
    except MaintenanceError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
