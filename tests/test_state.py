import unittest
from datetime import timedelta

from ctr import state

from helpers import T0, TempPathsCase, ts


class StateTest(TempPathsCase):
    def test_missing_file_means_never_consented(self):
        self.assertIsNone(state.load(self.paths.state))
        self.assertFalse(state.is_recording(None))

    def test_enable_disable_windows(self):
        self.enable(at=0)
        st = state.load(self.paths.state)
        self.assertTrue(state.is_recording(st))
        self.assertTrue(state.in_window(st, ts(5)))
        self.assertFalse(state.in_window(st, ts(-5)))

        state.disable(self.paths.state, T0 + timedelta(seconds=10))
        st = state.load(self.paths.state)
        self.assertFalse(state.is_recording(st))
        self.assertTrue(state.in_window(st, ts(5)))
        self.assertFalse(state.in_window(st, ts(15)))

        self.enable(at=20)
        st = state.load(self.paths.state)
        self.assertEqual(len(st.windows), 2)
        self.assertFalse(state.in_window(st, ts(15)), "disabled gap must stay excluded")
        self.assertTrue(state.in_window(st, ts(25)))

    def test_enable_twice_keeps_one_open_window(self):
        self.enable(at=0)
        self.enable(at=5)
        self.assertEqual(len(state.load(self.paths.state).windows), 1)

    def test_corrupt_file_fails_closed(self):
        self.paths.root.mkdir(parents=True)
        self.paths.state.write_text("{not json", encoding="utf-8")
        st = state.load(self.paths.state)
        self.assertIsNotNone(st)
        self.assertFalse(state.is_recording(st))
        self.enable(at=0)
        self.assertTrue(state.is_recording(state.load(self.paths.state)))

    def test_unparseable_timestamp_is_outside_window(self):
        self.enable(at=0)
        self.assertFalse(state.in_window(state.load(self.paths.state), "yesterday"))

    def test_cwd_scope(self):
        self.enable(at=0, scope_cwds=[r"D:\ctr-testbed"])
        st = state.load(self.paths.state)
        self.assertTrue(state.cwd_in_scope(st, r"D:\ctr-testbed"))
        self.assertTrue(state.cwd_in_scope(st, r"d:\CTR-TESTBED\sub"))
        self.assertFalse(state.cwd_in_scope(st, r"D:\ctr-testbed2"))
        self.assertFalse(state.cwd_in_scope(st, None))
        self.enable(at=1, scope_cwds=[])
        self.assertTrue(state.cwd_in_scope(state.load(self.paths.state), r"C:\anything"))


if __name__ == "__main__":
    unittest.main()
