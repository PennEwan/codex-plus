import io
import json
import shutil
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ctr import hook, state, store, timeutil
from ctr.paths import Paths

T0 = datetime(2026, 10, 28, 10, 0, 0, tzinfo=timezone.utc)


def ts(seconds: float) -> str:
    return timeutil.iso(T0 + timedelta(seconds=seconds))


class TempPathsCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="ctr-test-"))
        self.paths = Paths(self.tmp / "data")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def enable(self, at: float = 0, **kw):
        return state.enable(self.paths.state, T0 + timedelta(seconds=at), **kw)

    def run_hook(self, payload, env=None):
        out = io.StringIO()
        raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        code = hook.main(stdin=io.BytesIO(raw), stdout=out, paths=self.paths, env=env or {})
        self.assertEqual(code, 0)
        text = out.getvalue()
        return json.loads(text) if text else None

    def events(self):
        return list(store.iter_events(self.paths))

    def kinds(self):
        return [e["kind"] for e in self.events()]


def write_rollout(path: Path, records, trailing_partial: str | None = None):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        if trailing_partial:
            f.write(trailing_partial)


def rec(t: float, rtype: str, payload: dict) -> dict:
    return {"timestamp": ts(t), "type": rtype, "payload": payload}
