"""Operation log for troubleshooting. Only fixed identifiers and numbers — never free text.

A line looks like `2026-10-28T12:00:00Z redeem succeeded status=201 ms=84`. There is
deliberately no parameter that could carry a CDK, token, email or backend message.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 256 * 1024
_IDENT = re.compile(r"^[a-z_]{1,32}$")


def write(path: Path, op: str, outcome: str, status: int | None = None, ms: int | None = None) -> None:
    if not (_IDENT.match(op) and _IDENT.match(outcome)):
        raise ValueError("log fields must be fixed identifiers")
    parts = [datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), op, outcome]
    if isinstance(status, int):
        parts.append(f"status={status}")
    if isinstance(ms, int):
        parts.append(f"ms={ms}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > MAX_BYTES:
            keep = path.read_bytes()[-MAX_BYTES // 2:]
            path.write_bytes(keep[keep.find(b"\n") + 1:])
        with open(path, "a", encoding="utf-8") as f:
            f.write(" ".join(parts) + "\n")
    except OSError:
        pass
