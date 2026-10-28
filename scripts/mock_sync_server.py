"""Local mock of the task-data sync backend (docs/sync-api.md). For development and tests only.

    python scripts\\mock_sync_server.py [--port 18788] [--store mock-sync.json] [-v]

`--store` keeps devices and events in a JSON file across restarts (to check that a client
resuming after the backend was down creates no duplicates). The request log shows method,
path and status only — never event content or tokens.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import socket
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 4 * 1024 * 1024
EVENT_SCHEMA = "ctr.event/v2"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class State:
    def __init__(self, store: Path | None = None):
        self.lock = threading.Lock()
        self.store = store
        self.devices: dict[str, dict] = {}   # device_token -> {device_id, created_at, revoked}
        self.events: dict[str, dict] = {}    # device_id -> {event_id: event}
        self.stats: dict[str, dict] = {}     # device_id -> counters
        self.fail_next: list[dict] = []
        self.envelopes: list[dict] = []     # each batch without its events (schema, capabilities…)
        self.requests: list[tuple[str, str]] = []
        self.client_headers: list[str] = []
        if store and store.exists():
            doc = json.loads(store.read_text(encoding="utf-8"))
            self.devices, self.events, self.stats = doc["devices"], doc["events"], doc["stats"]

    def save(self) -> None:
        if not self.store:
            return
        tmp = self.store.with_suffix(".tmp")
        tmp.write_text(json.dumps({"devices": self.devices, "events": self.events, "stats": self.stats},
                                  ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.store)

    def counters(self, device_id: str) -> dict:
        return self.stats.setdefault(device_id, {"batches": 0, "accepted": 0, "duplicates": 0, "rejected": 0})

    def all_events(self) -> list[dict]:
        out = []
        for device_id, events in self.events.items():
            out += [{**e, "_device_id": device_id} for e in events.values()]
        return sorted(out, key=lambda e: (e["_device_id"], str(e.get("session_id")), e.get("seq") or 0))


def _valid_event(e: object) -> bool:
    return (isinstance(e, dict) and isinstance(e.get("event_id"), str) and e["event_id"]
            and isinstance(e.get("session_id"), str) and isinstance(e.get("seq"), int)
            and e.get("schema") == EVENT_SCHEMA)


class Handler(BaseHTTPRequestHandler):
    server_version = "ctr-sync-mock/0.1"

    @property
    def state(self) -> State:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, fmt, *args):  # only method, path, status — never bodies
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    # ---- plumbing -------------------------------------------------------------------------
    def _send(self, status: int, body: dict, headers: dict | None = None) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _error(self, status: int, code: str, headers: dict | None = None) -> None:
        self._send(status, {"error": {"code": code}}, headers)

    def _raw_body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _json(self, raw: bytes) -> object:
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, ValueError):
            return None

    def _device(self) -> dict | None:
        """The authenticated device, or None after an error response was sent."""
        auth = self.headers.get("Authorization") or ""
        token = auth[7:] if auth.startswith("Bearer ") else ""
        dev = self.state.devices.get(token)
        if not dev:
            self._error(401, "device_invalid")
            return None
        if dev.get("revoked"):
            self._error(403, "device_revoked")
            return None
        return dev

    def _injected_failure(self, raw: bytes) -> str | None:
        """Apply /_mock/fail-next. Returns 'drop_after_store' when the batch must be stored first."""
        if not self.state.fail_next:
            return None
        rule = self.state.fail_next[0]
        if rule.get("path") and rule["path"] != self.path:  # only fail requests to that path
            return None
        if rule.get("mode") == "drop_after_store":
            if self.path != "/v1/events/batch":
                return None
            self.state.fail_next.pop(0)
            return "drop_after_store"
        rule["count"] = rule.get("count", 1) - 1
        if rule["count"] <= 0:
            self.state.fail_next.pop(0)
        status = int(rule.get("status", 503))
        headers = {"Retry-After": str(rule.get("retry_after", 1))} if status == 429 else {}
        if rule.get("location"):
            headers["Location"] = rule["location"]
        self._error(status, rule.get("code") or ("rate_limited" if status == 429 else "injected"), headers)
        return "sent"

    def _route(self, method: str) -> None:
        self.state.requests.append((method, self.path))
        self.state.client_headers.append(self.headers.get("X-Ctr-Client") or "")
        raw = self._raw_body() if method in ("POST", "DELETE") else b""
        if self.path.startswith("/_mock/"):
            return self._control(method, raw)
        with self.state.lock:
            injected = self._injected_failure(raw)
            if injected == "sent":
                return
            if method == "POST" and self.path == "/v1/devices":
                return self._register(raw)
            dev = self._device()
            if dev is None:
                return
            if method == "GET" and self.path == "/v1/devices/me":
                return self._me(dev)
            if method == "POST" and self.path == "/v1/events/batch":
                return self._batch(dev, raw, drop=injected == "drop_after_store")
            if method == "DELETE" and self.path == "/v1/devices/me/data":
                deleted = len(self.state.events.pop(dev["device_id"], {}))
                self.state.save()
                return self._send(200, {"deleted_events": deleted})
            if method == "DELETE" and self.path == "/v1/devices/me":
                token = next(t for t, d in self.state.devices.items() if d is dev)
                del self.state.devices[token]
                self.state.save()
                return self._send(200, {"revoked": True})
        self._error(404, "not_found")

    def do_GET(self):
        self._route("GET")

    def do_POST(self):
        self._route("POST")

    def do_DELETE(self):
        self._route("DELETE")

    # ---- API ------------------------------------------------------------------------------
    def _register(self, raw: bytes) -> None:
        body = self._json(raw)
        consent = body.get("consent") if isinstance(body, dict) else None
        if not isinstance(consent, dict) or not isinstance(consent.get("version"), int):
            return self._error(400, "invalid_request")
        token = "ctrd_" + secrets.token_urlsafe(24)
        dev = {"device_id": "dev_" + secrets.token_hex(8), "created_at": _now(), "revoked": False}
        self.state.devices[token] = dev
        self.state.save()
        self._send(201, {"device_id": dev["device_id"], "device_token": token, "created_at": dev["created_at"]})

    def _me(self, dev: dict) -> None:
        events = self.state.events.get(dev["device_id"], {})
        sessions = {e.get("session_id") for e in events.values()}
        last = max((e.get("recorded_at") or "" for e in events.values()), default=None)
        self._send(200, {"device_id": dev["device_id"], "event_count": len(events),
                         "session_count": len(sessions), "last_event_at": last,
                         "created_at": dev["created_at"]})

    def _batch(self, dev: dict, raw: bytes, drop: bool) -> None:
        if len(raw) > MAX_BODY:
            return self._error(413, "batch_too_large")
        body = self._json(raw)
        if not isinstance(body, dict) or not isinstance(body.get("events"), list):
            return self._error(400, "invalid_batch")
        self.state.envelopes.append({k: v for k, v in body.items() if k != "events"})
        store = self.state.events.setdefault(dev["device_id"], {})
        counters = self.state.counters(dev["device_id"])
        counters["batches"] += 1
        results = []
        for e in body["events"]:
            if not _valid_event(e):
                eid = e.get("event_id") if isinstance(e, dict) else None
                results.append({"event_id": eid, "status": "rejected", "error": {"code": "invalid_event"}})
                counters["rejected"] += 1
            elif e["event_id"] in store:
                results.append({"event_id": e["event_id"], "status": "duplicate"})
                counters["duplicates"] += 1
            else:
                store[e["event_id"]] = {**e, "_arrival": sum(len(v) for v in self.state.events.values())}
                results.append({"event_id": e["event_id"], "status": "accepted"})
                counters["accepted"] += 1
        self.state.save()
        if drop:  # stored, but the client never hears back
            self.close_connection = True
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            return
        n = {s: sum(1 for r in results if r["status"] == s) for s in ("accepted", "duplicate", "rejected")}
        self._send(200, {"accepted": n["accepted"], "duplicates": n["duplicate"], "rejected": n["rejected"],
                         "results": results})

    # ---- control --------------------------------------------------------------------------
    def _control(self, method: str, raw: bytes) -> None:
        with self.state.lock:
            if method == "POST" and self.path == "/_mock/fail-next":
                rule = self._json(raw)
                if not isinstance(rule, dict):
                    return self._error(400, "invalid_request")
                self.state.fail_next.append(rule)
                return self._send(200, {"queued": len(self.state.fail_next)})
            if method == "POST" and self.path == "/_mock/revoke-all":
                for dev in self.state.devices.values():
                    dev["revoked"] = True
                self.state.save()
                return self._send(200, {"revoked": len(self.state.devices)})
            if method == "GET" and self.path == "/_mock/events":
                return self._send(200, {"events": self.state.all_events()})
            if method == "GET" and self.path == "/_mock/envelopes":
                return self._send(200, {"envelopes": self.state.envelopes})
            if method == "GET" and self.path == "/_mock/stats":
                return self._send(200, {"devices": len(self.state.devices), "stats": self.state.stats,
                                        "events": {d: len(e) for d, e in self.state.events.items()}})
        self._error(404, "not_found")


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if getattr(self, "verbose", False):
            super().handle_error(request, client_address)


def make_server(host: str, port: int, store: Path | None = None, verbose: bool = False) -> Server:
    server = Server((host, port), Handler)
    server.state = State(store)  # type: ignore[attr-defined]
    server.verbose = verbose  # type: ignore[attr-defined]
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description="Mock task-data sync backend (development only)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18788)
    parser.add_argument("--store", type=Path, help="persist devices and events in this JSON file")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    server = make_server(args.host, args.port, args.store, args.verbose)
    print(f"mock sync backend on http://{args.host}:{server.server_address[1]}  (Ctrl+C to stop)")
    sys.stdout.flush()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
