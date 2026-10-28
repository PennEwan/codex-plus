"""Live check of the `/充值` hook through the App kernel's app-server (same protocol as the desktop App).

Run only after the codex-cdk-recharge hook is trusted in the Codex App (cdkr.cmd status).

    python scripts\\live_recharge_hook.py [--with-normal]

Checks: is `/充值` blocked before the model, is it written to the rollout, does the window
process outlive the hook, what the hook costs. `--with-normal` also sends one ordinary
low-effort prompt (consumes model quota) to measure the hook's overhead on normal prompts.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins" / "codex-task-recorder" / "lib"))

from ctr import kernel  # noqa: E402
from ctr.appserver import AppServer  # noqa: E402

TESTBED = r"D:\ctr-testbed"
OUT = REPO / ".testdata" / "live"
SELECTOR = "codex-cdk-recharge@ctr-local"
PROBE = "ZZPROBE-NOT-A-CDK-7731"  # stands in for a CDK typed after the command


def window_pids() -> list[int]:
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\" | "
          "Where-Object { $_.CommandLine -like '*cdkr.window*' } | ForEach-Object { $_.ProcessId }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True).stdout
    return [int(x) for x in out.split() if x.isdigit()]


def text_input(text: str) -> list[dict]:
    return [{"type": "text", "text": text, "text_elements": []}]


def run_turn(s: AppServer, tid: str, text: str, **overrides) -> dict:
    mark = s.mark()
    started = time.monotonic()
    res = s.request("turn/start", {"threadId": tid, "input": text_input(text), **overrides})
    turn_id = res["turn"]["id"]
    done = s.wait_for(lambda m: m.get("method") == "turn/completed" and m["params"]["turn"]["id"] == turn_id,
                      timeout=300, after=mark)
    seconds = round(time.monotonic() - started, 2)
    msgs = s.notifications[mark:]
    hooks = [m["params"]["run"] for m in msgs if m.get("method") == "hook/completed"
             and m["params"].get("turnId") == turn_id]
    ours = [h for h in hooks if "codex-cdk-recharge" in str(h.get("sourcePath", ""))]
    item_types = sorted({(m["params"].get("item") or {}).get("type") for m in msgs
                         if m.get("method") in ("item/started", "item/completed")} - {None})
    turn = done["params"]["turn"]
    return {"turn_id": turn_id, "status": turn.get("status"), "error": turn.get("error"), "seconds": seconds,
            "item_types": item_types, "model_output": any(t in item_types for t in ("agentMessage", "reasoning")),
            "our_hook": [{"status": h.get("status"), "durationMs": h.get("durationMs"),
                          "entries": h.get("entries")} for h in ours],
            "all_hook_statuses": [(h.get("eventName"), h.get("status")) for h in hooks]}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-normal", action="store_true")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    exe, version = kernel.find_app_kernel()
    results: dict = {"kernel_version": version}
    s = AppServer(exe, TESTBED, OUT / "appserver-recharge.jsonl")
    before = set(window_pids())
    try:
        s.initialize()
        hooks = s.plugin_hooks(TESTBED, SELECTOR)
        results["hook_trust"] = [h.get("trustStatus") for h in hooks]
        print("hook trust:", results["hook_trust"])
        if not hooks or any(h.get("trustStatus") != "trusted" for h in hooks):
            print("The /充值 hook is not trusted yet; trust it in the Codex App first.")
            return 2
        thread = s.request("thread/start", {"cwd": TESTBED, "approvalPolicy": "never",
                                            "sandbox": "workspace-write"})["thread"]
        results["thread_id"], rollout = thread["id"], thread.get("path")

        results["command"] = run_turn(s, thread["id"], "/充值", effort="low")
        time.sleep(3)
        spawned = [p for p in window_pids() if p not in before]
        results["window_alive_after_hook"] = bool(spawned)
        print("[/充值]", json.dumps(results["command"], ensure_ascii=False))
        print("window processes started:", spawned)

        results["command_with_text"] = run_turn(s, thread["id"], f"/充值 {PROBE}", effort="low")
        print("[/充值 <text>]", json.dumps(results["command_with_text"], ensure_ascii=False))

        if args.with_normal:
            results["normal"] = run_turn(s, thread["id"], "只回复 ok 两个字母。", effort="low")
            print("[normal]", json.dumps(results["normal"], ensure_ascii=False))

        time.sleep(1.5)
        text = Path(rollout).read_text(encoding="utf-8") if rollout and Path(rollout).exists() else ""
        results["rollout_path_present"] = bool(text)
        results["rollout_has_command"] = "/充值" in text or "\\u5145\\u503c" in text
        results["rollout_has_probe"] = PROBE in text
        recorder = Path.home() / "AppData" / "Local" / "CodexTaskRecorder" / "sessions"
        hits = [str(p) for p in recorder.rglob("*.jsonl") if PROBE in p.read_text(encoding="utf-8", errors="replace")]
        results["recorder_files_with_probe"] = hits
        print("rollout written:", results["rollout_path_present"], "| has /充值:", results["rollout_has_command"],
              "| has probe text:", results["rollout_has_probe"], "| recorder files with probe:", hits)
    finally:
        s.close()
        for pid in set(window_pids()) - before:
            subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    (OUT / "recharge-hook-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                                    encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
