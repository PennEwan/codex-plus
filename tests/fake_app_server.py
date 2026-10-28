"""Stand-in for `codex app-server` (JSON-RPC over stdio) used by test_cdkr_account.

Mode comes from argv[1]: ok | error | hang | exit.
"""
import json
import sys

mode = sys.argv[1] if len(sys.argv) > 1 else "ok"
if mode == "exit":
    sys.exit(3)
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:  # a notification such as `initialized`
        continue
    if msg["method"] == "initialize":
        reply = {"id": msg["id"], "result": {"userAgent": "fake"}}
    elif mode == "hang":
        continue
    elif mode == "error":
        reply = {"id": msg["id"], "error": {"code": -32600, "message": "nope"}}
    else:
        reply = {"id": msg["id"], "result": {"echo": msg["method"], "params": msg["params"]}}
    print(json.dumps({"method": "configWarning", "params": {}}), flush=True)  # noise before the reply
    print("not json", flush=True)
    print(json.dumps(reply), flush=True)
