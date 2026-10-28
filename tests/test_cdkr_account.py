import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from cdkr import account, flow


class ParseAccountTest(unittest.TestCase):
    """Shapes taken from a real `account/read` on App kernel 0.163.0-alpha.10.2 (values replaced)."""

    def test_chatgpt_login(self):
        result = {"account": {"type": "chatgpt", "email": "a@example.com", "planType": "plus"},
                  "requiresOpenaiAuth": True,
                  "workspaceRouting": {"chatgptAccountId": "acct-1", "backendOrigin": "https://chatgpt.com"}}
        self.assertEqual(account.parse_account(result), flow.Account("acct-1", "a@example.com", "plus"))

    def assertKind(self, result, kind):
        with self.assertRaises(flow.AccountError) as ctx:
            account.parse_account(result)
        self.assertEqual(ctx.exception.kind, kind)

    def test_not_logged_in(self):
        self.assertKind({"account": None, "requiresOpenaiAuth": True}, flow.NOT_LOGGED_IN)

    def test_other_login_types(self):
        self.assertKind({"account": {"type": "apiKey"}}, flow.NOT_CHATGPT)
        self.assertKind({"account": {"type": "amazonBedrock"}}, flow.NOT_CHATGPT)

    def test_missing_identity_fields(self):
        self.assertKind({"account": {"type": "chatgpt", "email": None, "planType": "free"},
                         "workspaceRouting": {"chatgptAccountId": "acct-1"}}, flow.READ_FAILED)
        self.assertKind({"account": {"type": "chatgpt", "email": "a@example.com", "planType": "free"}},
                        flow.READ_FAILED)
        self.assertKind("garbage", flow.READ_FAILED)


FAKE = [sys.executable, str(Path(__file__).with_name("fake_app_server.py"))]


class AppServerRequestTest(unittest.TestCase):
    def test_initializes_then_returns_the_matching_result(self):
        result = account.app_server_request(FAKE + ["ok"], "account/read", {"refreshToken": False}, 20)
        self.assertEqual(result, {"echo": "account/read", "params": {"refreshToken": False}})

    def test_error_reply(self):
        with self.assertRaises(RuntimeError):
            account.app_server_request(FAKE + ["error"], "account/read", {}, 20)

    def test_server_exits(self):
        with self.assertRaises(RuntimeError):
            account.app_server_request(FAKE + ["exit"], "account/read", {}, 20)

    def test_no_reply_times_out_and_returns(self):
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            account.app_server_request(FAKE + ["hang"], "account/read", {}, 1.0)
        self.assertLess(time.monotonic() - started, 8)


class FindKernelTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cdkr-kernel-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_picks_newest_kernel_without_running_anything(self):
        bin_root = self.tmp / "OpenAI" / "Codex" / "bin"
        old, new = bin_root / "aaa" / "codex.exe", bin_root / "bbb" / "codex.exe"
        for i, exe in enumerate((old, new)):
            exe.parent.mkdir(parents=True)
            exe.write_bytes(b"")
            os.utime(exe, (time.time() - 100 + i * 50,) * 2)
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.tmp), "CDKR_CODEX_BIN": ""}), \
                mock.patch("subprocess.run", side_effect=AssertionError("no subprocess")):
            self.assertEqual(account.find_kernel(), new)

    def test_missing_app(self):
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.tmp), "CDKR_CODEX_BIN": ""}):
            self.assertIsNone(account.find_kernel())
            with self.assertRaises(flow.AccountError) as ctx:
                account.read_account()
            self.assertEqual(ctx.exception.kind, flow.KERNEL_MISSING)


if __name__ == "__main__":
    unittest.main()
