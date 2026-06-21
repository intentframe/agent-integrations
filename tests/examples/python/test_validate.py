#!/usr/bin/env python3
"""Example using if_integration_bridge (same client external agents should use)."""

from __future__ import annotations

import sys

from if_integration_bridge import BridgeClient


def main() -> int:
    client = BridgeClient.from_env()
    with client:
        pre = client.validate_expect_status(
            {
                "action": "RUN_COMMAND",
                "command": "echo bridge-python-pre-handshake",
                "target": "echo bridge-python-pre-handshake",
                "reason": "Should require handshake first",
            },
            status_code=412,
        )
        if "handshake" not in str(pre.get("error", "")).lower():
            print(f"FAIL pre-handshake: unexpected body={pre!r}", file=sys.stderr)
            return 1
        print("PASS python pre-handshake: HTTP 412")

        ctx = client.handshake()
        print(f"PASS python handshake: session_id={ctx.get('session_id')!r}")

        ok = client.validate_run_command(
            command="echo bridge-python-ok",
            reason="Python bridge client example",
        )
        if not ok.get("allowed"):
            print(f"FAIL python benign: {ok!r}", file=sys.stderr)
            return 1
        print("PASS python benign: allowed=True")

        blocked = client.validate_run_command(
            command="sudo rm -rf /",
            reason="Should block",
        )
        if blocked.get("allowed"):
            print(f"FAIL python blocked: {blocked!r}", file=sys.stderr)
            return 1
        print(f"PASS python blocked: error={blocked.get('error')!r}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(exc, file=sys.stderr)
        raise SystemExit(1) from exc
