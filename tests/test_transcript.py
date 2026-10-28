import json
import unittest
from collections import Counter

from ctr import state, transcript

from helpers import TempPathsCase, rec, write_rollout


def item(t, turn, it):
    return rec(t, "event_msg", {"type": "item_completed", "turn_id": turn, "thread_id": "th",
                                "started_at_ms": 1, "completed_at_ms": 2, "item": it})


class TranscriptTest(TempPathsCase):
    def setUp(self):
        super().setUp()
        self.enable(at=0)
        self.st = state.load(self.paths.state)
        self.path = self.tmp / "rollout.jsonl"

    def ingest(self, offset=0, ctx=None):
        ctx = ctx or transcript.Context(session_id="s1", meta={})
        return transcript.ingest(str(self.path), offset, self.st, ctx, 1 << 20), ctx

    def by_kind(self, events):
        out = {}
        for e in events:
            out.setdefault(e["kind"], []).append(e)
        return out

    def test_maps_known_records(self):
        write_rollout(self.path, [
            rec(-100, "session_meta", {"id": "th", "cli_version": "0.163.0-alpha.10.2",
                                       "originator": "Codex Desktop", "source": "vscode",
                                       "model_provider": "openai", "base_instructions": "SYSTEM PROMPT",
                                       "creator_account_id": "acct-secret"}),
            rec(1, "turn_context", {"turn_id": "t1", "model": "gpt-a", "effort": "low", "summary": "auto",
                                    "approval_policy": "on-request",
                                    "sandbox_policy": {"type": "workspace-write", "network_access": False}}),
            rec(2, "event_msg", {"type": "task_started", "turn_id": "t1", "started_at": 5,
                                 "turn_attribution": {"root_turn_id": "t1", "parent_turn_id": None}}),
            item(3, "t1", {"type": "UserMessage", "id": "u1", "content": [{"type": "text", "text": "list files"}]}),
            item(4, "t1", {"type": "Reasoning", "id": "r1", "summary_text": [], "raw_content": ["hidden"]}),
            item(5, "t1", {"type": "Reasoning", "id": "r2", "summary_text": ["Looking at files"]}),
            rec(6, "response_item", {"type": "function_call", "name": "shell", "call_id": "call_a",
                                     "arguments": json.dumps({"command": ["dir"]})}),
            rec(7, "response_item", {"type": "function_call_output", "call_id": "call_a",
                                     "output": "Exit code: 0\nfile.txt"}),
            item(8, "t1", {"type": "CommandExecution", "id": "exec-1", "command": "dir /x", "exit_code": 1,
                           "status": "failed", "aggregated_output": "oops",
                           "duration": {"secs": 1, "nanos": 500_000_000}}),
            item(9, "t1", {"type": "McpToolCall", "id": "mcp-1", "server": "srv", "tool": "t",
                           "arguments": {"q": 1}, "result": None, "error": {"message": "bad"},
                           "status": "failed"}),
            item(10, "t1", {"type": "AgentMessage", "id": "a1", "phase": "final",
                            "content": [{"type": "text", "text": "Done."}]}),
            rec(11, "event_msg", {"type": "token_count", "info": {"total_token_usage": {"input_tokens": 9}},
                                  "rate_limits": {"credits": 3}}),
            rec(12, "response_item", {"type": "reasoning", "summary": [], "encrypted_content": "gAAAA"}),
            rec(13, "response_item", {"type": "message", "role": "assistant", "content": []}),
            rec(14, "world_state", {"full": True, "state": {}}),
            rec(15, "event_msg", {"type": "task_complete", "turn_id": "t1", "duration_ms": 10,
                                  "last_agent_message": "Done.", "error": {"message": "stream failed"}}),
            rec(16, "event_msg", {"type": "turn_aborted", "turn_id": "t2", "reason": "interrupted"}),
            rec(17, "mystery", {"type": "x"}),
            item(18, "t1", {"type": "WebSearch", "id": "w1", "query": "secret stuff"}),
        ])
        result, ctx = self.ingest()
        k = self.by_kind(result.events)

        meta = k["session_meta"][0]["data"]
        self.assertEqual(meta["cli_version"], "0.163.0-alpha.10.2")
        self.assertNotIn("creator_account_id", meta)
        self.assertEqual(meta["base_instructions"]["present"], True)
        self.assertNotIn("SYSTEM PROMPT", json.dumps(result.events))
        self.assertEqual(ctx.meta["originator"], "Codex Desktop")

        cfg = k["model_config"][0]
        self.assertEqual(cfg["data"]["reasoning_effort"], "low")
        self.assertEqual(cfg["data"]["sandbox_policy"], "workspace-write")

        self.assertEqual(k["user_prompt"][0]["data"]["text"], "list files")
        self.assertEqual(k["assistant_message"][0]["data"]["text"], "Done.")

        empty, filled = k["reasoning_summary"]
        self.assertEqual(empty["completeness"]["status"], "unavailable")
        self.assertNotIn("hidden", json.dumps(empty))
        self.assertEqual(filled["data"]["summary"], "Looking at files")

        call = k["tool_call"][0]
        self.assertEqual((call["tool_use_id"], call["granularity"]), ("call_a", "model_tool_call"))
        outcomes = {e["source"]["name"]: e["data"]["outcome"] for e in k["tool_result"]}
        self.assertEqual(outcomes["response_item/function_call_output"], "success")
        self.assertEqual(outcomes["event_msg/item_completed:CommandExecution"], "error")
        self.assertEqual(outcomes["event_msg/item_completed:McpToolCall"], "error")
        cmd = next(e for e in k["tool_result"] if e["data"].get("tool_name") == "CommandExecution")
        self.assertEqual(cmd["data"]["duration_ms"], 1500)

        self.assertNotIn("rate_limits", json.dumps(k["token_usage"]))
        self.assertEqual(k["turn_error"][0]["data"]["message"], "stream failed")
        self.assertEqual(k["turn_interrupted"][0]["data"]["reason"], "interrupted")
        self.assertEqual(k["turn_start"][0]["relations"]["root_turn_id"], "t1")

        s = result.stats
        self.assertEqual(s["omitted:encrypted_reasoning"], 1)
        self.assertEqual(s["omitted:reasoning_raw_content"], 1)
        self.assertEqual(s["omitted:rate_limits"], 1)
        self.assertEqual(s["omitted:world_state"], 1)
        self.assertEqual(s["other:mystery"], 1)
        self.assertEqual(s["other:item/WebSearch"], 1)
        self.assertNotIn("secret stuff", json.dumps(result.events))
        self.assertTrue(all(e["source"]["type"] in ("transcript", "derived") for e in result.events))
        self.assertTrue(all(e["source_ts"] for e in result.events))

    def test_partial_last_line_waits_and_offset_resumes(self):
        line = rec(1, "event_msg", {"type": "turn_aborted", "turn_id": "t", "reason": "x"})
        partial = json.dumps(line)[:20]
        write_rollout(self.path, [line], trailing_partial=partial)
        first, ctx = self.ingest()
        self.assertEqual(len(first.events), 1)
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line)[20:] + "\n")
        second, _ = self.ingest(first.offset, ctx)
        self.assertEqual(len(second.events), 1)
        third, _ = self.ingest(second.offset, ctx)
        self.assertEqual(third.events, [])

    def test_model_change_from_turn_context(self):
        write_rollout(self.path, [
            rec(1, "turn_context", {"turn_id": "t1", "model": "gpt-a", "effort": "low"}),
            rec(2, "turn_context", {"turn_id": "t2", "model": "gpt-b", "effort": "low"}),
        ])
        result, ctx = self.ingest()
        changed = [e for e in result.events if e["kind"] == "model_changed"]
        self.assertEqual(changed[0]["data"], {"from": "gpt-a", "to": "gpt-b"})
        self.assertEqual(changed[0]["turn_id"], "t2")
        self.assertEqual(ctx.last_model, "gpt-b")

    def test_sensitive_call_output_dropped(self):
        write_rollout(self.path, [
            rec(1, "response_item", {"type": "custom_tool_call", "name": "exec", "call_id": "c9",
                                     "input": "fs.readFileSync('C:/Users/a/.codex/auth.json')"}),
            rec(2, "response_item", {"type": "custom_tool_call_output", "call_id": "c9",
                                     "output": '{"tokens": {"access": "abc"}}'}),
        ])
        result, _ = self.ingest()
        out = next(e for e in result.events if e["kind"] == "tool_result")
        self.assertEqual(out["data"]["output"], "[REDACTED:sensitive_file]")
        self.assertEqual(out["redaction"]["counts"]["sensitive_file"], 1)

    def test_missing_file_is_counted_not_raised(self):
        result = transcript.ingest(str(self.tmp / "nope.jsonl"), 0, self.st,
                                   transcript.Context(session_id="s", meta={}), 1024)
        self.assertEqual(result.stats, Counter(unreadable_transcript=1))

    def test_truncated_file_rewinds(self):
        write_rollout(self.path, [rec(1, "event_msg", {"type": "turn_aborted", "turn_id": "t"})])
        result, _ = self.ingest(offset=10_000)
        self.assertEqual(result.stats["transcript_rewound"], 1)
        self.assertEqual(len(result.events), 1)


if __name__ == "__main__":
    unittest.main()
