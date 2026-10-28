import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from cdkr import launch, single


class CommandTest(unittest.TestCase):
    def test_window_runs_under_pythonw_with_plugin_lib_on_path(self):
        argv, env = launch.window_command({"PYTHONPATH": "C:\\other"})
        self.assertEqual(Path(argv[0]).name.lower(), "pythonw.exe" if os.name == "nt" else Path(sys.executable).name)
        self.assertEqual(argv[1:], ["-m", "cdkr.window"])
        self.assertEqual(env["PYTHONPATH"].split(os.pathsep)[0], str(launch.LIB_DIR))
        self.assertTrue((launch.LIB_DIR / "cdkr" / "window.py").exists())

    def test_spawn_detaches_and_inherits_no_handles(self):
        calls = []

        def fake_popen(argv, **kw):
            calls.append(kw)
            return mock.Mock()

        with mock.patch("subprocess.Popen", fake_popen):
            self.assertTrue(launch.open_window())
        kw = calls[0]
        self.assertTrue(kw["close_fds"])
        for stream in ("stdin", "stdout", "stderr"):
            self.assertIs(kw[stream], subprocess.DEVNULL)
        if os.name == "nt":
            self.assertTrue(kw["creationflags"] & launch.DETACHED_PROCESS)

    @unittest.skipUnless(os.name == "nt", "job breakaway is Windows-only")
    def test_retries_without_breakaway_when_job_forbids_it(self):
        flags = []

        def fake_popen(argv, **kw):
            flags.append(kw["creationflags"])
            if kw["creationflags"] & launch.CREATE_BREAKAWAY_FROM_JOB:
                raise PermissionError(5, "Access is denied")
            return mock.Mock()

        with mock.patch("subprocess.Popen", fake_popen):
            self.assertTrue(launch.open_window())
        self.assertEqual(len(flags), 2)
        self.assertFalse(flags[1] & launch.CREATE_BREAKAWAY_FROM_JOB)

    @unittest.skipUnless(os.name == "nt", "Windows process semantics")
    def test_hook_returns_while_child_keeps_running(self):
        # A hook-like parent spawns a long-lived child the way open_window does and exits at once;
        # its stdout pipe must close immediately (Codex waits for it), the child must live on.
        child = "import time; time.sleep(3)"
        parent = (f"import subprocess, sys; sys.path.insert(0, {str(launch.LIB_DIR)!r}); "
                  "from cdkr import launch; "
                  f"p = launch.spawn([sys.executable, '-c', {child!r}], dict(__import__('os').environ)); "
                  "print(p.pid)")
        started = time.monotonic()
        out = subprocess.run([sys.executable, "-c", parent], capture_output=True, text=True, timeout=10)
        self.assertLess(time.monotonic() - started, 2.5, "parent's stdout stayed open")
        pid = int(out.stdout.strip())
        alive = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        self.assertIn(str(pid), alive.stdout)


@unittest.skipUnless(os.name == "nt", "named mutex is Windows-only")
class SingleInstanceTest(unittest.TestCase):
    def test_second_acquire_in_same_session_fails(self):
        name = f"Local\\cdkr-test-{os.getpid()}"
        first = single.acquire(name)
        self.assertIsNotNone(first)
        self.assertIsNone(single.acquire(name))
        single.release(first)
        again = single.acquire(name)
        self.assertIsNotNone(again)
        single.release(again)


if __name__ == "__main__":
    unittest.main()
