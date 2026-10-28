"""Read who is logged in to Codex through the App kernel's official `account/read`.

We start our own short-lived `codex app-server` from the App's kernel and ask it; nothing
attaches to the running App and no credential file is read. `account/read` returns the
email, plan and ChatGPT account id — never a token. `refreshToken` stays false so we never
race the App for a token refresh.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from . import __version__
from .flow import KERNEL_MISSING, NOT_CHATGPT, NOT_LOGGED_IN, READ_FAILED, Account, AccountError

CREATE_NO_WINDOW = 0x08000000


def find_kernel() -> Path | None:
    r"""Newest %LOCALAPPDATA%\OpenAI\Codex\bin\<hash>\codex.exe (the App installs updates there)."""
    override = os.environ.get("CDKR_CODEX_BIN")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    root = Path(local) / "OpenAI" / "Codex" / "bin" if local else None
    if root is None or not root.is_dir():
        return None
    candidates = [p for p in root.glob("*/codex.exe") if p.is_file()]
    return max(candidates, key=lambda p: p.stat().st_mtime) if candidates else None


def parse_account(result: object) -> Account:
    if not isinstance(result, dict):
        raise AccountError(READ_FAILED)
    acct = result.get("account")
    if not acct:
        raise AccountError(NOT_LOGGED_IN)
    if not isinstance(acct, dict):
        raise AccountError(READ_FAILED)
    if acct.get("type") != "chatgpt":
        raise AccountError(NOT_CHATGPT)
    routing = result.get("workspaceRouting") if isinstance(result.get("workspaceRouting"), dict) else {}
    account_id, email, plan = routing.get("chatgptAccountId"), acct.get("email"), acct.get("planType")
    if not (isinstance(account_id, str) and account_id and isinstance(email, str) and "@" in email):
        raise AccountError(READ_FAILED)
    return Account(account_id, email, plan if isinstance(plan, str) else None)


def read_account(timeout: float = 25.0) -> Account:
    exe = find_kernel()
    if exe is None or not exe.exists():
        raise AccountError(KERNEL_MISSING)
    try:
        result = app_server_request([str(exe), "app-server"], "account/read", {"refreshToken": False}, timeout)
    except (OSError, TimeoutError, RuntimeError, ValueError):
        raise AccountError(READ_FAILED) from None
    return parse_account(result)


def app_server_request(argv: list[str], method: str, params: dict, timeout: float) -> dict:
    """One JSON-RPC call to a fresh app-server process (`argv`), which is then shut down."""
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, cwd=tempfile.gettempdir(),
                            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0)
    lines: queue.Queue = queue.Queue()

    def pump() -> None:
        for raw in proc.stdout:
            lines.put(raw)
        lines.put(None)

    threading.Thread(target=pump, daemon=True).start()
    deadline = time.monotonic() + timeout

    def send(msg: dict) -> None:
        proc.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        proc.stdin.flush()

    def wait(rid: int) -> dict:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                raise TimeoutError(method)
            try:
                raw = lines.get(timeout=left)
            except queue.Empty:
                raise TimeoutError(method) from None
            if raw is None:
                raise RuntimeError("app-server exited")
            try:
                msg = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            if isinstance(msg, dict) and msg.get("id") == rid and "method" not in msg:
                if "error" in msg:
                    raise RuntimeError("app-server error")
                return msg.get("result") or {}

    try:
        send({"id": 1, "method": "initialize",
              "params": {"clientInfo": {"name": "codex_cdk_recharge", "title": "Codex CDK Recharge",
                                        "version": __version__}}})
        wait(1)
        send({"method": "initialized", "params": {}})
        send({"id": 2, "method": method, "params": params})
        return wait(2)
    finally:
        try:
            proc.stdin.close()
            proc.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            proc.kill()
