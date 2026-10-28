"""Live acceptance scenarios against the Codex App kernel. Consumes model quota.

Run only after the plugin's hooks are trusted (ctr status shows "trusted 12").
Each scenario talks to our own `codex app-server` (same protocol and kernel as
the desktop App) or to `codex exec`, inside D:\\ctr-testbed only.

    python scripts/live_tests.py --alt-model gpt-5.6-luna
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "plugins" / "codex-task-recorder" / "lib"))

from ctr import kernel, store  # noqa: E402
from ctr.appserver import AppServer  # noqa: E402
from ctr.paths import PLUGIN_SELECTOR, Paths  # noqa: E402

TESTBED = r"D:\ctr-testbed"
OUT = REPO / ".testdata" / "live"


def text_input(text: str) -> list[dict]:
    return [{"type": "text", "text": text, "text_elements": []}]


def run_turn(s: AppServer, thread_id: str, text: str, timeout: float = 600, **overrides) -> dict:
    mark = s.mark()
    res = s.request("turn/start", {"threadId": thread_id, "input": text_input(text), **overrides})
    turn_id = res["turn"]["id"]
    done = s.wait_for(lambda m: m.get("method") == "turn/completed"
                      and m["params"]["turn"]["id"] == turn_id, timeout=timeout, after=mark)
    return done["params"]["turn"]


def events_for_turn(turn_id: str) -> list[dict]:
    return [e for e in store.iter_events(Paths.default()) if e.get("turn_id") == turn_id]


def ctr(*args: str) -> str:
    proc = subprocess.run([sys.executable, "-m", "ctr", *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8",
                               "PYTHONPATH": str(REPO / "plugins/codex-task-recorder/lib")})
    return (proc.stdout + proc.stderr).strip()


def hook_runs(s: AppServer) -> dict:
    runs: dict = defaultdict(lambda: {"statuses": Counter(), "entries": Counter(), "sources": Counter()})
    for m in s.notifications:
        if m.get("method") != "hook/completed":
            continue
        run = m["params"]["run"]
        r = runs[run.get("eventName")]
        r["statuses"][run.get("status")] += 1
        r["sources"][run.get("source")] += 1
        for entry in run.get("entries") or []:
            r["entries"][f'{entry.get("kind")}: {str(entry.get("text"))[:120]}'] += 1
    return {k: {kk: dict(vv) for kk, vv in v.items()} for k, v in runs.items()}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--alt-model", default="gpt-5.6-luna")
    ap.add_argument("--effort", default="low")
    ap.add_argument("--skip-exec", action="store_true")
    ap.add_argument("--model", help="base model for the thread (default: Codex config)")
    ap.add_argument("--only", help="comma-separated scenario numbers, e.g. 1,2")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    exe, version = kernel.find_app_kernel()
    print(f"kernel: {exe} ({version})")
    results: dict = {"kernel_version": version, "scenarios": {}}
    only = set(args.only.split(",")) if args.only else None

    def want(name: str) -> bool:
        return only is None or name.split("_")[0] in only

    s = AppServer(exe, TESTBED, OUT / "appserver.jsonl")
    try:
        s.initialize()
        hooks = s.plugin_hooks(TESTBED, PLUGIN_SELECTOR)
        trust = Counter(h["trustStatus"] for h in hooks)
        results["hook_trust"] = dict(trust)
        print("hook trust:", dict(trust))
        if trust.get("trusted", 0) != len(hooks) or not hooks:
            print("Hooks are not all trusted; trust them in the Codex App first.")
            return 2

        start = {"cwd": TESTBED, "approvalPolicy": "never", "sandbox": "workspace-write"}
        if args.model:
            start["model"] = args.model
        thread = s.request("thread/start", start)["thread"]
        tid = thread["id"]
        results["thread_id"] = tid
        print("thread:", tid)

        def scenario(name: str, text: str, **overrides) -> dict | None:
            if not want(name):
                return None
            started = time.time()
            turn = run_turn(s, tid, text, effort=args.effort, **overrides)
            time.sleep(1.5)  # let the Stop hook finish writing
            recorded = Counter(e["kind"] for e in events_for_turn(turn["id"]))
            info = {"turn_id": turn["id"], "status": turn["status"], "error": turn.get("error"),
                    "seconds": round(time.time() - started, 1), "recorded_kinds": dict(recorded)}
            results["scenarios"][name] = info
            print(f"[{name}] {turn['status']} in {info['seconds']}s → {dict(recorded)}")
            return info

        scenario("1_普通对话", "用一句话解释什么是 JSONL 文件。", summary="detailed")
        scenario("2_工具调用", "请在当前目录依次运行两个命令：`echo ctr-ok` 和 `ctr-no-such-cmd-xyz`，"
                               "然后用一句话分别报告两个命令的结果。", summary="detailed")
        scenario("3_模型切换", "用一句话复述上一步两个命令的结果。", model=args.alt_model, summary="detailed")

        if not want("4"):
            results["hook_runs"] = hook_runs(s)
            return finish(results)
        # 4. Interrupt: start a long command, then turn/interrupt (what the App's stop button sends).
        mark = s.mark()
        res = s.request("turn/start", {"threadId": tid, "effort": args.effort, "input": text_input(
            "请运行命令 `ping -n 90 127.0.0.1`，等它完全结束后再总结输出。")})
        turn_id = res["turn"]["id"]
        try:
            s.wait_for(lambda m: m.get("method") == "item/started"
                       and (m["params"].get("item") or {}).get("type") == "commandExecution", timeout=180,
                       after=mark)
            results["interrupt_point"] = "during commandExecution"
            time.sleep(3)
        except TimeoutError:
            print("[4_任务中断] no command started within 180s; interrupting anyway")
            results["interrupt_point"] = "before any command started"
        s.request("turn/interrupt", {"threadId": tid, "turnId": turn_id})
        done = s.wait_for(lambda m: m.get("method") == "turn/completed"
                          and m["params"]["turn"]["id"] == turn_id, timeout=120, after=mark)["params"]["turn"]
        time.sleep(2)
        recorded = Counter(e["kind"] for e in events_for_turn(turn_id))
        results["scenarios"]["4_任务中断"] = {"turn_id": turn_id, "status": done["status"],
                                           "recorded_kinds": dict(recorded)}
        print(f"[4_任务中断] {done['status']} → {dict(recorded)}")

        # 5. Stop control: after `ctr disable` nothing from the next turn may be recorded.
        print(ctr("disable"))
        info = scenario("5_停止后不记录", "回复：ok")
        info["passed"] = not info["recorded_kinds"]
        print(ctr("enable", "--i-consent", "--cwd", TESTBED).splitlines()[-1])
        results["hook_runs"] = hook_runs(s)
    finally:
        s.close()

    if not args.skip_exec and want("6"):
        # 6. Same kernel through `codex exec` (CLI surface).
        proc = subprocess.run([str(exe), "exec", "--skip-git-repo-check", "-C", TESTBED, "--json",
                               "-c", f'model_reasoning_effort="{args.effort}"',
                               "运行命令 `echo exec-ok`，然后只回复命令输出。"],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=600)
        (OUT / "exec.jsonl").write_text(proc.stdout, encoding="utf-8")
        thread_id = next((json.loads(l).get("thread_id") for l in proc.stdout.splitlines()
                          if '"thread.started"' in l), None)
        time.sleep(2)
        recorded = Counter(e["kind"] for e in store.iter_events(Paths.default()) if e["session_id"] == thread_id)
        results["scenarios"]["6_exec"] = {"thread_id": thread_id, "exit": proc.returncode,
                                          "recorded_kinds": dict(recorded)}
        print(f"[6_exec] exit={proc.returncode} → {dict(recorded)}")

    return finish(results)


def finish(results: dict) -> int:
    name = "results-" + time.strftime("%H%M%S") + ".json"
    (OUT / name).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("results:", OUT / name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
