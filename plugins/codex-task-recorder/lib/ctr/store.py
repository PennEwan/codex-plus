"""Per-session JSONL files and cursors, written under a per-session file lock.

Several hook processes can run at once (e.g. PostToolUse and Stop), so every
append and cursor update for one session happens inside the same lock.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from . import timeutil
from .paths import Paths, safe_name

LOCK_TIMEOUT_S = 2.0

if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class LockTimeout(Exception):
    pass


class SessionHandle:
    def __init__(self, paths: Paths, session_id: str, cursor: dict):
        self.paths = paths
        self.session_id = session_id
        self.cursor = cursor

    @property
    def events_file(self) -> Path:
        return self.paths.sessions / self.cursor["day"] / f"{safe_name(self.session_id)}.jsonl"

    def append(self, events: list[dict]) -> None:
        if not events:
            return
        path = self.events_file
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)
        with open(path, "ab") as f:
            f.write(payload.encode("utf-8"))
        self.cursor["event_count"] = self.cursor.get("event_count", 0) + len(events)
        self.cursor["last_event_at"] = events[-1]["recorded_at"]


@contextmanager
def session(paths: Paths, session_id: str) -> Iterator[SessionHandle]:
    paths.cursors.mkdir(parents=True, exist_ok=True)
    name = safe_name(session_id)
    lock_path = paths.cursors / f"{name}.lock"
    cursor_path = paths.cursors / f"{name}.json"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while not _try_lock(fd):
            if time.monotonic() > deadline:
                raise LockTimeout(session_id)
            time.sleep(0.02)
        try:
            cursor = json.loads(cursor_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            cursor = {"session_id": session_id, "day": timeutil.now().strftime("%Y-%m-%d"),
                      "transcripts": {}}
        handle = SessionHandle(paths, session_id, cursor)
        try:
            yield handle
        finally:
            tmp = cursor_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(handle.cursor, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, cursor_path)
            _unlock(fd)
    finally:
        os.close(fd)


def iter_events(paths: Paths) -> Iterator[dict]:
    """Every recorded event, file by file (used by status and report)."""
    if not paths.sessions.exists():
        return
    for file in sorted(paths.sessions.glob("*/*.jsonl")):
        with open(file, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except ValueError:
                        continue
