"""Bridge HTTP-over-UDS integration tests (httpx, no client library)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

from if_security_backend.agent_config import default_test_agent_pack_path, load_agent_pack
from if_security_backend.bridge.runner import is_bridge_running
from if_security_backend.runtime.health import core_healthy
from if_security_backend.runtime.paths import bridge_socket_path


def _bridge_client(secret: str) -> httpx.Client:
    socket = bridge_socket_path()
    if not socket.exists():
        raise FileNotFoundError(f"Bridge socket missing: {socket}")
    transport = httpx.HTTPTransport(uds=str(socket))
    return httpx.Client(
        transport=transport,
        base_url="http://bridge",
        timeout=120.0,
        headers={"Authorization": f"Bearer {secret}"},
    )


def run_bridge_connection_tests(agent_config: Path | None = None) -> int:
    if not core_healthy():
        print("Core is not healthy — run: if-integration-backend start", file=sys.stderr)
        return 1
    if not is_bridge_running():
        print("Bridge is not running — run: if-integration-backend start", file=sys.stderr)
        return 1

    pack = load_agent_pack(agent_config or default_test_agent_pack_path())
    os.environ.setdefault("INTENTFRAME_USER_ID", pack.user_id)
    os.environ.setdefault("INTENTFRAME_AGENT_ID", pack.agent_id)

    with _bridge_client(pack.bridge_secret) as client:
        health = client.get("/health")
        if health.status_code != 200:
            print(f"FAIL bridge health: status={health.status_code} body={health.text!r}")
            return 1
        print("PASS bridge health: HTTP 200")

        pre = client.post(
            "/validate",
            json={
                "action": "RUN_COMMAND",
                "command": "echo bridge-pre-handshake",
                "target": "echo bridge-pre-handshake",
                "reason": "Should require handshake first",
            },
        )
        if pre.status_code != 412:
            print(f"FAIL bridge pre-handshake: expected 412 status={pre.status_code} body={pre.text!r}")
            return 1
        pre_body = pre.json()
        if "handshake" not in str(pre_body.get("error", "")).lower():
            print(f"FAIL bridge pre-handshake: unexpected body={pre_body!r}")
            return 1
        print("PASS bridge pre-handshake: HTTP 412")

        hs = client.post("/handshake", json={})
        if hs.status_code != 200:
            print(f"FAIL bridge handshake: status={hs.status_code} body={hs.text!r}")
            return 1
        hs_body = hs.json()
        if not hs_body.get("session_id"):
            print(f"FAIL bridge handshake: missing session_id body={hs_body!r}")
            return 1
        print(f"PASS bridge handshake: session_id={hs_body.get('session_id')!r}")

        ok = client.post(
            "/validate",
            json={
                "action": "RUN_COMMAND",
                "command": "echo if-backend-bridge-ok",
                "target": "echo if-backend-bridge-ok",
                "reason": "Bridge connection benign",
            },
        )
        if ok.status_code != 200:
            print(f"FAIL bridge benign: status={ok.status_code} body={ok.text!r}")
            return 1
        ok_body = ok.json()
        if not ok_body.get("allowed"):
            print(f"FAIL bridge benign: expected allowed=True body={ok_body!r}")
            return 1
        print("PASS bridge benign: allowed=True")

        blocked = client.post(
            "/validate",
            json={
                "action": "RUN_COMMAND",
                "command": "sudo rm -rf /",
                "target": "sudo rm -rf /",
                "reason": "Should be blocked",
            },
        )
        if blocked.status_code != 200:
            print(f"FAIL bridge blocked: status={blocked.status_code} body={blocked.text!r}")
            return 1
        blocked_body = blocked.json()
        if blocked_body.get("allowed"):
            print(f"FAIL bridge blocked: expected allowed=False body={blocked_body!r}")
            return 1
        print(f"PASS bridge blocked: error={blocked_body.get('error')!r}")

    return 0
