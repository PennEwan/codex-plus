"""Filesystem locations used by the recorder."""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "CodexTaskRecorder"
PLUGIN_NAME = "codex-task-recorder"
MARKETPLACE_NAME = "ctr-local"
PLUGIN_SELECTOR = f"{PLUGIN_NAME}@{MARKETPLACE_NAME}"

_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,128}$")


def default_root() -> Path:
    override = os.environ.get("CTR_DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / APP_DIR_NAME
    return Path.home() / ".codex-task-recorder"


def safe_name(value: str) -> str:
    """Turn a session id into a file name; anything unusual gets hashed."""
    if _SAFE_NAME.match(value) and value not in (".", ".."):
        return value
    return "sid-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:32]


@dataclass(frozen=True)
class Paths:
    root: Path

    @classmethod
    def default(cls) -> "Paths":
        return cls(default_root())

    @property
    def state(self) -> Path:
        return self.root / "state.json"

    @property
    def sessions(self) -> Path:
        return self.root / "sessions"

    @property
    def cursors(self) -> Path:
        return self.root / "cursors"

    @property
    def notices(self) -> Path:
        return self.root / "notices"

    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def log(self) -> Path:
        return self.root / "recorder.log"
