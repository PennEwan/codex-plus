"""Codex UserPromptSubmit hook entry point: `/充值` opens the CDK window.

It must never break the user's prompt: whatever happens, it exits 0. If the plugin's
library cannot be loaded, `/充值…` is still blocked here (it may carry a CDK), using
nothing but the standard library.
"""
import json
import os
import sys

_LIB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib")
sys.path.insert(0, _LIB)


def _fallback(raw: bytes) -> None:
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
        prompt = payload.get("prompt") if isinstance(payload, dict) else None
        if isinstance(prompt, str) and prompt.lstrip().startswith(("/充值", "／充值")):
            reason = "充值插件没能加载，这条消息已拦下、没有发给模型。请重新安装充值插件。"
            sys.stdout.write(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=True))
            sys.stdout.flush()
    except BaseException:  # noqa: BLE001
        pass


try:
    from cdkr.trigger import main
except BaseException:  # a broken install must not break the user's session
    try:
        _fallback(sys.stdin.buffer.read())
    except BaseException:  # noqa: BLE001
        pass
    sys.exit(0)

sys.exit(main())
