import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

from ctr import cli

LISTING = r"""Marketplace `ctr-local`
D:\codex-task-recorder\.agents\plugins\marketplace.json

PLUGIN                               STATUS              VERSION        SOURCE
codex-task-recorder@ctr-local        installed, enabled  0.1.0          D:\x
codex-cdk-recharge@ctr-local         installed, enabled  0.1.0          D:\y
"""


class UninstallTest(unittest.TestCase):
    def run_uninstall(self, listing):
        calls = []

        def fake_run(exe, args, timeout=180):
            calls.append(args)
            return mock.Mock(returncode=0, stdout=listing if args == ["plugin", "list"] else "", stderr="")

        with mock.patch.object(cli.kernel, "find_app_kernel", return_value=("codex.exe", "x")), \
                mock.patch.object(cli.kernel, "run", fake_run), redirect_stdout(io.StringIO()):
            self.assertTrue(cli.uninstall_plugin())
        return calls

    def test_keeps_shared_marketplace_while_recharge_plugin_is_installed(self):
        calls = self.run_uninstall(LISTING)
        self.assertIn(["plugin", "remove", "codex-task-recorder@ctr-local"], calls)
        self.assertNotIn(["plugin", "marketplace", "remove", "ctr-local"], calls)

    def test_keeps_marketplace_when_plugin_list_fails(self):
        calls = []

        def fake_run(exe, args, timeout=180):
            calls.append(args)
            return mock.Mock(returncode=1 if args == ["plugin", "list"] else 0, stdout="", stderr="")

        with mock.patch.object(cli.kernel, "find_app_kernel", return_value=("codex.exe", "x")),                 mock.patch.object(cli.kernel, "run", fake_run), redirect_stdout(io.StringIO()):
            cli.uninstall_plugin()
        self.assertNotIn(["plugin", "marketplace", "remove", "ctr-local"], calls)

    def test_removes_marketplace_when_nothing_else_uses_it(self):
        calls = self.run_uninstall(LISTING.replace("codex-cdk-recharge@ctr-local         installed, enabled  0.1.0",
                                                   "codex-cdk-recharge@ctr-local         not installed      "))
        self.assertIn(["plugin", "marketplace", "remove", "ctr-local"], calls)


if __name__ == "__main__":
    unittest.main()
