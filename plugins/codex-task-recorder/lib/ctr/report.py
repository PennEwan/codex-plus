"""Event coverage report: what each hook and transcript source actually delivered."""
from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

from . import timeutil
from .hook import DOCUMENTED_FIELDS
from .paths import Paths
from .store import iter_events

HOOK_EVENTS = list(DOCUMENTED_FIELDS)

REQUIREMENTS = [
    ("用户已提交的 Prompt", ["user_prompt"]),
    ("模型公开返回的消息", ["assistant_message"]),
    ("模型名称及配置", ["model_config", "session_meta", "model_changed"]),
    ("工具调用", ["tool_call"]),
    ("工具执行结果", ["tool_result"]),
    ("工具 / 回合错误", ["tool_result:error", "turn_error"]),
    ("公开推理摘要", ["reasoning_summary"]),
    ("回合生命周期 / 中断", ["turn_start", "turn_end", "turn_interrupted"]),
    ("子代理 / 压缩 / 权限请求", ["subagent_start", "subagent_stop", "compaction", "permission_request"]),
]


def _matches(event: dict, selector: str) -> bool:
    kind, _, outcome = selector.partition(":")
    if event.get("kind") != kind:
        return False
    return not outcome or (event.get("data") or {}).get("outcome") == outcome


def _originator(event: dict, by_session: dict) -> str:
    return event["source"].get("originator") or by_session.get(event.get("session_id")) or "未知"


def build(events: list[dict]) -> dict:
    by_session_origin: dict[str, str] = {}
    for e in events:
        o = e["source"].get("originator")
        if o:
            by_session_origin.setdefault(e["session_id"], o)

    # 1. Hook support matrix, from hook_invocation diagnostics.
    hooks: dict = {name: {"invocations": Counter(), "payload_keys": set(), "transcript_path_present": Counter(),
                          "first_seen": None, "max_duration_ms": 0.0, "shell": Counter()}
                   for name in HOOK_EVENTS}
    env_seen: dict[str, set] = defaultdict(set)
    for e in events:
        if e["kind"] != "hook_invocation":
            continue
        name = e["source"]["name"]
        h = hooks.setdefault(name, {"invocations": Counter(), "payload_keys": set(),
                                    "transcript_path_present": Counter(), "first_seen": None,
                                    "max_duration_ms": 0.0, "shell": Counter()})
        d = e["data"]
        h["invocations"][_originator(e, by_session_origin)] += 1
        h["payload_keys"].update(d.get("payload_keys") or [])
        h["transcript_path_present"][bool(d.get("transcript_path_present"))] += 1
        h["first_seen"] = min(filter(None, [h["first_seen"], e["recorded_at"]]))
        h["max_duration_ms"] = max(h["max_duration_ms"], d.get("duration_ms") or 0)
        chain = d.get("process_chain") or []
        if chain:
            h["shell"][chain[0]] += 1
        for k, v in (d.get("env") or {}).items():
            if v not in (None, False):
                env_seen[k].add(str(v))

    # 2. Requirement coverage by source.
    coverage = []
    for label, selectors in REQUIREMENTS:
        matched = [e for e in events if any(_matches(e, s) for s in selectors)]
        by_source = Counter(f'{e["source"]["type"]}:{e["source"]["name"]}' for e in matched)
        status = Counter(e["completeness"]["status"] for e in matched)
        missing = Counter(m for e in matched for m in e["completeness"]["missing"])
        coverage.append({"requirement": label, "events": len(matched), "by_source": dict(by_source),
                         "completeness": dict(status), "top_missing": missing.most_common(5)})

    # 3. Identifiers and timestamps.
    content = [e for e in events if e["kind"] not in ("hook_invocation", "transcript_other", "recorder_notice")]
    ids = {
        "events": len(content),
        "with_session_id": sum(1 for e in content if e.get("session_id")),
        "with_turn_id": sum(1 for e in content if e.get("turn_id")),
        "with_source_ts": sum(1 for e in content if e.get("source_ts")),
        "tool_events_with_tool_use_id": sum(1 for e in content if e["kind"] in ("tool_call", "tool_result")
                                            and e.get("tool_use_id")),
        "tool_events": sum(1 for e in content if e["kind"] in ("tool_call", "tool_result")),
    }

    # 4. Scenarios per session.
    sessions: dict[str, list] = defaultdict(list)
    for e in events:
        sessions[e["session_id"]].append(e)
    scenarios = []
    for sid, evs in sessions.items():
        kinds = Counter(e["kind"] for e in evs)
        models = {(e.get("data") or {}).get("model") for e in evs if e["kind"] == "model_config"} - {None}
        scenarios.append({
            "session_id": sid,
            "originator": by_session_origin.get(sid, "未知"),
            "普通对话": bool(kinds["user_prompt"] and kinds["assistant_message"]),
            "工具调用": bool(kinds["tool_call"] or kinds["tool_result"]),
            "工具失败": any(_matches(e, "tool_result:error") for e in evs),
            "模型切换": bool(kinds["model_changed"]) or len(models) > 1,
            "任务中断": bool(kinds["turn_interrupted"]),
            "models": sorted(models),
            "interrupt_sources": sorted({e["source"]["name"] for e in evs if e["kind"] == "turn_interrupted"}),
            "events": len(evs),
        })

    # 5. Cross-source consistency.
    hook_prompts = {(e["session_id"], e.get("turn_id")): (e["data"] or {}).get("text")
                    for e in events if e["kind"] == "user_prompt" and e["source"]["type"] == "hook"}
    tr_prompts = {(e["session_id"], e.get("turn_id")): (e["data"] or {}).get("text")
                  for e in events if e["kind"] == "user_prompt" and e["source"]["type"] == "transcript"}
    shared = set(hook_prompts) & set(tr_prompts)
    hook_calls = {e.get("tool_use_id") for e in events
                  if e["kind"] in ("tool_call", "tool_result") and e["source"]["type"] == "hook"} - {None}
    model_calls = {e.get("tool_use_id") for e in events
                   if e["kind"] == "tool_call" and e.get("granularity") == "model_tool_call"} - {None}
    ui_items = {e.get("item_id"): e for e in events
                if e["kind"] == "tool_result" and e.get("granularity") == "ui_item" and e.get("item_id")}
    hook_results = [e for e in events if e["kind"] == "tool_result" and e["source"]["type"] == "hook"]
    unknown = [e for e in hook_results if (e["data"] or {}).get("outcome") == "unknown"]
    resolved = [e for e in unknown if e.get("tool_use_id") in ui_items
                and ui_items[e["tool_use_id"]]["data"].get("outcome") in ("success", "error")]
    cross = {
        "prompt_turns_hook": len(hook_prompts), "prompt_turns_transcript": len(tr_prompts),
        "prompt_turns_both": len(shared),
        "prompt_text_equal": sum(1 for k in shared if (hook_prompts[k] or "").strip() == (tr_prompts[k] or "").strip()),
        "tool_ids_hook": len(hook_calls), "tool_ids_transcript_model_calls": len(model_calls),
        "tool_ids_both": len(hook_calls & model_calls),
        "transcript_calls_without_hook": len(model_calls - hook_calls),
        "ui_items": len(ui_items),
        "hook_ids_matching_ui_items": len(hook_calls & set(ui_items)),
        "ui_items_without_hook": sorted(Counter(ui_items[i]["data"].get("tool_name") for i in set(ui_items) - hook_calls).items()),
        "hook_results_outcome_unknown": len(unknown),
        "hook_results_outcome_resolved_via_transcript": len(resolved),
    }

    omitted = Counter()
    for e in events:
        if e["kind"] == "transcript_other":
            omitted.update(e["data"].get("counts") or {})
    redactions = Counter()
    for e in events:
        redactions.update(e["redaction"]["counts"])

    return {
        "generated_at": timeutil.iso(timeutil.now()),
        "total_events": len(events),
        "codex_versions": sorted({e["source"].get("codex_version") for e in events} - {None}),
        "originators": sorted(set(by_session_origin.values())),
        "hooks": {k: {"invocations": dict(v["invocations"]), "total": sum(v["invocations"].values()),
                      "payload_keys": sorted(v["payload_keys"]),
                      "transcript_path_present": {str(b): n for b, n in v["transcript_path_present"].items()},
                      "first_seen": v["first_seen"], "max_duration_ms": v["max_duration_ms"],
                      "shell": dict(v["shell"])}
                  for k, v in hooks.items()},
        "hook_env": {k: sorted(v) for k, v in env_seen.items()},
        "coverage": coverage,
        "identifiers": ids,
        "scenarios": scenarios,
        "cross_source": cross,
        "transcript_omitted_or_unmapped": dict(omitted),
        "redactions": dict(redactions),
    }


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({(100 * n / d):.0f}%)" if d else "0/0"


def render(r: dict) -> str:
    yes = lambda b: "✅" if b else "—"  # noqa: E731
    out = [f"# 事件覆盖率报告", "",
           f"- 生成时间：{r['generated_at']}",
           f"- 事件总数：{r['total_events']}",
           f"- Codex 内核版本：{', '.join(r['codex_versions']) or '未知'}",
           f"- 来源客户端（originator）：{', '.join(r['originators']) or '未知'}", "",
           "## 1. Hook 支持矩阵（实测）", "",
           "| Hook 事件 | 触发次数（按客户端） | transcript_path 非空 | 最大耗时 ms | 启动 Shell | 实际输入字段 |",
           "|---|---|---|---|---|---|"]
    for name, h in r["hooks"].items():
        inv = ", ".join(f"{k}: {v}" for k, v in h["invocations"].items()) or "**未观测到**"
        tp = h["transcript_path_present"]
        tp_text = f"{tp.get('True', 0)}/{h['total']}" if h["total"] else "—"
        shell = ", ".join(h["shell"]) or "—"
        keys = ", ".join(f"`{k}`" for k in h["payload_keys"]) or "—"
        out.append(f"| {name} | {inv} | {tp_text} | {h['max_duration_ms'] or '—'} | {shell} | {keys} |")
    if r["hook_env"]:
        out += ["", "Hook 进程环境（实测）：", ""]
        out += [f"- `{k}` = {', '.join(f'`{v}`' for v in vals)}" for k, vals in r["hook_env"].items()]

    out += ["", "## 2. 需求覆盖矩阵", "",
            "| 需求 | 事件数 | 来源（类型:名称 → 条数） | 完整度分布 | 常见缺失字段 |", "|---|---|---|---|---|"]
    for c in r["coverage"]:
        src = "<br>".join(f"{k} → {v}" for k, v in sorted(c["by_source"].items())) or "**无**"
        comp = ", ".join(f"{k}: {v}" for k, v in c["completeness"].items()) or "—"
        miss = ", ".join(f"{k}×{n}" for k, n in c["top_missing"]) or "—"
        out.append(f"| {c['requirement']} | {c['events']} | {src} | {comp} | {miss} |")

    i = r["identifiers"]
    out += ["", "## 3. 时间戳与关联关系", "",
            f"- 带会话 ID：{_pct(i['with_session_id'], i['events'])}",
            f"- 带回合（turn）ID：{_pct(i['with_turn_id'], i['events'])}",
            f"- 带来源时间戳 source_ts：{_pct(i['with_source_ts'], i['events'])}（Hook 输入不含时间戳，此类事件只有 recorded_at）",
            f"- 工具事件带 tool_use_id：{_pct(i['tool_events_with_tool_use_id'], i['tool_events'])}"
            "（UI 条目使用 item_id，与 call_id 不同）",
            "", "## 4. 场景检查（按会话）", "",
            "| 会话 | 客户端 | 普通对话 | 工具调用 | 工具失败 | 模型切换 | 任务中断 | 模型 | 中断证据来源 |",
            "|---|---|---|---|---|---|---|---|---|"]
    for s in r["scenarios"]:
        out.append(f"| `{s['session_id'][:13]}…` | {s['originator']} | {yes(s['普通对话'])} | {yes(s['工具调用'])} | "
                   f"{yes(s['工具失败'])} | {yes(s['模型切换'])} | {yes(s['任务中断'])} | {', '.join(s['models']) or '—'} | "
                   f"{', '.join(s['interrupt_sources']) or '—'} |")
    x = r["cross_source"]
    out += ["", "## 5. 来源交叉一致性", "",
            f"- Prompt：Hook {x['prompt_turns_hook']} 个回合，transcript {x['prompt_turns_transcript']} 个回合，"
            f"两者都有 {x['prompt_turns_both']} 个，其中文本一致 {x['prompt_text_equal']} 个",
            f"- 工具调用 ID（UI 条目粒度）：Hook 涉及 {x['tool_ids_hook']} 个 ID，transcript UI 工具条目 {x['ui_items']} 个，"
            f"其中 {x['hook_ids_matching_ui_items']} 个能与 Hook 对上；**Hook 未覆盖的 UI 条目**："
            + (", ".join(f"{k} × {v}" for k, v in x["ui_items_without_hook"]) or "无"),
            f"- 工具调用 ID（模型调用粒度）：transcript 模型级调用 {x['tool_ids_transcript_model_calls']} 个，与 Hook 重合 "
            f"{x['tool_ids_both']} 个（Hook 按单条命令触发，模型级调用如 code-mode `exec` 一次可执行多条命令）",
            f"- Hook 工具结果无法判定成败 {x['hook_results_outcome_unknown']} 条（PostToolUse 只给输出文本，不给退出码），"
            f"其中 {x['hook_results_outcome_resolved_via_transcript']} 条可通过 tool_use_id = item_id 从 transcript 退出码补全",
            "", "## 6. 按策略省略 / 未映射的 transcript 记录（只计数，不存内容）", ""]
    out += [f"- `{k}`: {v}" for k, v in sorted(r["transcript_omitted_or_unmapped"].items())] or ["- 无"]
    out += ["", "## 7. 脱敏统计", ""]
    out += [f"- `{k}`: {v}" for k, v in sorted(r["redactions"].items())] or ["- 无"]
    return "\n".join(out) + "\n"


def write(paths: Paths, copy_to: Path | None = None) -> tuple[Path, Path]:
    events = list(iter_events(paths))
    r = build(events)
    paths.reports.mkdir(parents=True, exist_ok=True)
    stamp = timeutil.now().strftime("%Y%m%d-%H%M%S")
    md = paths.reports / f"coverage-{stamp}.md"
    js = paths.reports / f"coverage-{stamp}.json"
    md.write_text(render(r), encoding="utf-8")
    js.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    if copy_to:
        copy_to.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(md, copy_to)
    return md, js
