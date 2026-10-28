"""UserPromptSubmit hook: `/充值` opens the recharge window and keeps the prompt away from the model.

Contract with Codex: always exit 0; print nothing for ordinary prompts, and only the
block decision for `/充值`. The prompt itself is never logged or echoed.
"""
from __future__ import annotations

import json
import sys

COMMANDS = ("/充值", "／充值")  # full-width slash: Chinese IME in full-width mode
REASON_OPENED = "已打开充值窗口，这条消息没有发给模型。CDK 请只在充值窗口中输入。"
REASON_EXTRA_TEXT = ("已打开充值窗口，这条消息已拦下、没有发给模型。"
                     "为保护 CDK，请不要把 CDK 写在 /充值 后面，只在充值窗口中输入。")
REASON_LAUNCH_FAILED = "充值窗口没能打开，请双击安装目录中的「充值.cmd」。这条消息没有发给模型。"


def is_command(prompt: object) -> bool:
    return isinstance(prompt, str) and prompt.lstrip().startswith(COMMANDS)


def _default_launcher() -> bool:
    from .launch import open_window
    return open_window()


def main(stdin=None, stdout=None, launcher=None) -> int:
    try:
        out = handle((stdin if stdin is not None else sys.stdin.buffer).read(), launcher)
        if out:
            stdout = stdout if stdout is not None else sys.stdout
            stdout.write(json.dumps(out, ensure_ascii=True))
            stdout.flush()
    except BaseException:  # noqa: BLE001 - never break the user's prompt
        pass
    return 0


def handle(raw: bytes, launcher=None) -> dict | None:
    try:
        payload = json.loads(raw.decode("utf-8", "replace")) if raw else None
    except ValueError:
        return None
    if not isinstance(payload, dict) or payload.get("hook_event_name") != "UserPromptSubmit":
        return None
    prompt = payload.get("prompt")
    if not is_command(prompt):
        return None
    try:
        opened = bool((launcher or _default_launcher)())
    except Exception:  # noqa: BLE001 - the prompt is still blocked below
        opened = False
    if not opened:
        reason = REASON_LAUNCH_FAILED
    elif prompt.strip() not in COMMANDS:
        reason = REASON_EXTRA_TEXT
    else:
        reason = REASON_OPENED
    return {"decision": "block", "reason": reason}
