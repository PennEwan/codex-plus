import unittest

from ctr import report

from helpers import TempPathsCase, rec, write_rollout

SID = "sess-report"


def p(event, **kw):
    base = {"hook_event_name": event, "session_id": SID, "cwd": "D:/x", "model": "gpt-a",
            "permission_mode": "default", "turn_id": "t1"}
    base.update(kw)
    return base


class ReportTest(TempPathsCase):
    def setUp(self):
        super().setUp()
        self.enable(at=-3600)

    def test_matrix_scenarios_and_cross_source(self):
        rollout = self.tmp / "r.jsonl"
        write_rollout(rollout, [
            rec(0, "session_meta", {"cli_version": "0.163.0-alpha.10.2", "originator": "Codex Desktop"}),
            rec(1, "turn_context", {"turn_id": "t1", "model": "gpt-a", "effort": "low"}),
            rec(2, "event_msg", {"type": "item_completed", "turn_id": "t1",
                                 "item": {"type": "UserMessage", "id": "u", "content": [{"type": "text", "text": "go"}]}}),
            rec(3, "response_item", {"type": "function_call", "name": "shell", "call_id": "c1", "arguments": "{}"}),
            rec(4, "response_item", {"type": "function_call", "name": "apply_patch", "call_id": "c2", "arguments": "{}"}),
            rec(5, "event_msg", {"type": "item_completed", "turn_id": "t1",
                                 "item": {"type": "Reasoning", "id": "r", "summary_text": []}}),
            rec(6, "turn_context", {"turn_id": "t2", "model": "gpt-b", "effort": "low"}),
            rec(7, "event_msg", {"type": "turn_aborted", "turn_id": "t2", "reason": "interrupted"}),
        ])
        self.run_hook(p("UserPromptSubmit", prompt="go", transcript_path=str(rollout)))
        self.run_hook(p("PreToolUse", tool_name="Bash", tool_use_id="c1", tool_input={"command": "ls"}))
        self.run_hook(p("PostToolUse", tool_name="Bash", tool_use_id="c1", tool_input={"command": "ls"},
                        tool_response={"exit_code": 2}))
        self.run_hook(p("Stop", last_assistant_message="ok", stop_hook_active=False, transcript_path=str(rollout)))

        r = report.build(self.events())
        self.assertEqual(r["hooks"]["UserPromptSubmit"]["total"], 1)
        self.assertEqual(r["hooks"]["Interrupt"]["total"], 0)
        self.assertIn("Codex Desktop", r["originators"])
        self.assertEqual(r["codex_versions"], ["0.163.0-alpha.10.2"])

        cov = {c["requirement"]: c for c in r["coverage"]}
        self.assertGreaterEqual(cov["工具 / 回合错误"]["events"], 1)
        self.assertEqual(cov["公开推理摘要"]["completeness"], {"unavailable": 1})

        s = r["scenarios"][0]
        self.assertTrue(s["普通对话"] and s["工具调用"] and s["工具失败"] and s["模型切换"] and s["任务中断"])
        self.assertEqual(s["interrupt_sources"], ["event_msg/turn_aborted"])

        x = r["cross_source"]
        self.assertEqual(x["prompt_turns_both"], 1)
        self.assertEqual(x["prompt_text_equal"], 1)
        self.assertEqual(x["tool_ids_both"], 1)
        self.assertEqual(x["transcript_calls_without_hook"], 1)  # apply_patch never reached a hook

        md = report.render(r)
        self.assertIn("| Interrupt | **未观测到** |", md)

    def test_write_creates_files(self):
        self.run_hook(p("UserPromptSubmit", prompt="hello"))
        md, js = report.write(self.paths, copy_to=self.tmp / "copy.md")
        self.assertTrue(md.exists() and js.exists() and (self.tmp / "copy.md").exists())


if __name__ == "__main__":
    unittest.main()
