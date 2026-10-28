"""Shared fixtures for the codex-cdk-recharge tests: an in-process mock backend."""
import json
import sys
import threading
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mock_recharge_server  # noqa: E402


class MockBackend:
    def __init__(self):
        self.server = mock_recharge_server.make_server("127.0.0.1", 0)
        self.state = self.server.state
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self._thread = threading.Thread(target=self.server.serve_forever, args=(0.05,), daemon=True)
        self._thread.start()

    def post(self, path, body=None):
        req = urllib.request.Request(self.url + path, data=json.dumps(body or {}).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json"})
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with direct.open(req, timeout=5) as resp:
            return json.loads(resp.read() or b"{}")

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
