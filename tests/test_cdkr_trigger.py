import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cdkr import trigger


def run(payload, launcher=lambda: True):
    out = io.StringIO()
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    code = trigger.main(stdin=io.BytesIO(raw), stdout=out, launcher=launcher)
    text = out.getvalue()
    return code, (json.loads(text) if text else None)


def prompt(text):
    return {"hook_event_name": "UserPromptSubmit", "session_id": "s", "turn_id": "t", "prompt": text}


class TriggerTest(unittest.TestCase):
    def test_command_opens_window_and_blocks_prompt(self):
        launched = []
        code, out = run(prompt("/充值"), launcher=lambda: launched.append(1) or True)
        self.assertEqual(code, 0)
        self.assertEqual(launched, [1])
        self.assertEqual(out, {"decision": "block", "reason": trigger.REASON_OPENED})

    def test_text_after_command_is_still_blocked_with_cdk_warning(self):
        code, out = run(prompt("  /充值 ABCD-EFGH-1234 "))
        self.assertEqual(out["decision"], "block")
        self.assertEqual(out["reason"], trigger.REASON_EXTRA_TEXT)
        self.assertNotIn("ABCD", json.dumps(out))

    def test_full_width_slash_from_chinese_ime_also_counts(self):
        _, out = run(prompt("／充值"))
        self.assertEqual(out, {"decision": "block", "reason": trigger.REASON_OPENED})

    def test_launch_failure_still_blocks(self):
        def boom():
            raise OSError("no pythonw")
        _, out = run(prompt("/充值"), launcher=boom)
        self.assertEqual(out, {"decision": "block", "reason": trigger.REASON_LAUNCH_FAILED})

    def test_ordinary_prompts_pass_silently(self):
        for text in ["hello", "怎么 /充值？", "充值", "", None, 42]:
            launched = []
            code, out = run(prompt(text), launcher=lambda: launched.append(1) or True)
            self.assertEqual((code, out, launched), (0, None, []), text)

    def test_other_events_and_bad_input_pass_silently(self):
        for payload in [{"hook_event_name": "Stop", "prompt": "/充值"}, b"", b"not json", b"[1,2]",
                        "/充值".encode("utf-8")]:
            self.assertEqual(run(payload, launcher=lambda: self.fail("launched")), (0, None))

    def test_unreadable_stdin_exits_zero(self):
        class Broken:
            def read(self):
                raise OSError("pipe closed")
        self.assertEqual(trigger.main(stdin=Broken(), stdout=io.StringIO()), 0)

    def test_output_is_ascii_json(self):
        out = io.StringIO()
        trigger.main(stdin=io.BytesIO(json.dumps(prompt("/充值")).encode("utf-8")), stdout=out,
                     launcher=lambda: True)
        self.assertTrue(out.getvalue().isascii())


HOOK = Path(__file__).resolve().parents[1] / "plugins" / "codex-cdk-recharge" / "hooks" / "cdkr_hook.py"


def run_entry(script, payload):
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    proc = subprocess.run([sys.executable, str(script)], input=json.dumps(payload).encode("utf-8"),
                          capture_output=True, timeout=20, env=env)
    return proc.returncode, proc.stdout


class EntryScriptTest(unittest.TestCase):
    def test_ordinary_prompt_through_the_real_entry_prints_nothing(self):
        self.assertEqual(run_entry(HOOK, prompt("hello")), (0, b""))

    def test_broken_install_still_blocks_the_command(self):
        tmp = Path(tempfile.mkdtemp(prefix="cdkr-entry-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        (tmp / "hooks").mkdir()
        shutil.copy(HOOK, tmp / "hooks" / HOOK.name)  # no lib/ next to it: `import cdkr` fails
        code, out = run_entry(tmp / "hooks" / HOOK.name, prompt("/充值 ABCD-1234"))
        self.assertEqual(code, 0)
        decision = json.loads(out)
        self.assertEqual(decision["decision"], "block")
        self.assertNotIn("ABCD", out.decode("ascii"))
        self.assertEqual(run_entry(tmp / "hooks" / HOOK.name, prompt("hello")), (0, b""))


if __name__ == "__main__":
    unittest.main()
