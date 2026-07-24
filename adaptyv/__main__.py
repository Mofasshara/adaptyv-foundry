from __future__ import annotations

import json
import sys

from adaptyv.bridge import handle_request


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] != "--json":
        # Never signal failure via exit code (see module contract) — the "ok"
        # field is the only failure channel, so the caller can parse uniformly.
        print(json.dumps({"ok": False, "error": {
            "type": "BridgeError",
            "message": "usage: python -m adaptyv --json  (reads one JSON request from stdin)"}}))
        return
    raw = sys.stdin.read()
    try:
        request = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(json.dumps({"ok": False, "error": {"type": "BridgeError",
                                                  "message": f"invalid JSON on stdin: {exc}"}}))
        return
    print(json.dumps(handle_request(request)))


if __name__ == "__main__":
    main()
