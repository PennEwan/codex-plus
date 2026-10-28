"""Start the recharge window as an independent process.

The hook must return at once and the window must outlive it, so the child is detached,
breaks away from Codex's job object when allowed, and inherits no handles — an inherited
stdout pipe would keep Codex waiting on the hook until the window closes.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LIB_DIR = Path(__file__).resolve().parents[1]
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def _pythonw() -> str:
    exe = Path(sys.executable)
    windowed = exe.with_name("pythonw.exe")
    return str(windowed) if os.name == "nt" and windowed.exists() else str(exe)


def window_command(environ=None) -> tuple[list[str], dict]:
    env = dict(os.environ if environ is None else environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (str(LIB_DIR), env.get("PYTHONPATH")) if p)
    env["PYTHONIOENCODING"] = "utf-8"
    return [_pythonw(), "-m", "cdkr.window"], env


def spawn(argv: list[str], env: dict) -> subprocess.Popen:
    kw = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
              close_fds=True, env=env, cwd=str(LIB_DIR))
    if os.name != "nt":
        return subprocess.Popen(argv, start_new_session=True, **kw)
    base = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    try:
        return subprocess.Popen(argv, creationflags=base | CREATE_BREAKAWAY_FROM_JOB, **kw)
    except PermissionError:  # the job does not allow breakaway
        return subprocess.Popen(argv, creationflags=base, **kw)


def open_window() -> bool:
    argv, env = window_command()
    spawn(argv, env)
    return True
