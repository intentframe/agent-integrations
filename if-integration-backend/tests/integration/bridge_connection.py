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

REPO_ROOT = Path(__file__).resolve().parents[3]
TESTS_DIR = REPO_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from intentframe_validation_helpers import assert_bridge_semantic_delete  # noqa: E402


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

        if "WRITE_HOST_FILE" in pack.action_types:
            write_ok = client.post(
                "/validate",
                json={
                    "action": "WRITE_HOST_FILE",
                    "path": "~/bridge-test.txt",
                    "content": "hello",
                    "target": "~/bridge-test.txt",
                    "reason": "Bridge connection benign write",
                },
            )
            if write_ok.status_code != 200:
                print(f"FAIL bridge write benign: status={write_ok.status_code} body={write_ok.text!r}")
                return 1
            write_body = write_ok.json()
            if not write_body.get("allowed"):
                print(f"FAIL bridge write benign: expected allowed=True body={write_body!r}")
                return 1
            print("PASS bridge write benign: allowed=True")

            write_blocked = client.post(
                "/validate",
                json={
                    "action": "WRITE_HOST_FILE",
                    "path": "/etc/bridge-test-denied",
                    "content": "nope",
                    "target": "/etc/bridge-test-denied",
                    "reason": "Should be blocked by host path policy",
                },
            )
            if write_blocked.status_code != 200:
                print(
                    f"FAIL bridge write blocked: status={write_blocked.status_code} "
                    f"body={write_blocked.text!r}"
                )
                return 1
            write_blocked_body = write_blocked.json()
            if write_blocked_body.get("allowed"):
                print(f"FAIL bridge write blocked: expected allowed=False body={write_blocked_body!r}")
                return 1
            print(f"PASS bridge write blocked: error={write_blocked_body.get('error')!r}")

        if "DELETE_HOST_FILE" in pack.action_types:
            delete_benign = client.post(
                "/validate",
                json={
                    "action": "DELETE_HOST_FILE",
                    "path": "~/intentframe-bridge-delete-ok.txt",
                    "target": "~/intentframe-bridge-delete-ok.txt",
                    "reason": "Bridge delete home-path probe",
                },
            )
            if delete_benign.status_code != 200:
                print(
                    f"FAIL bridge delete home-path: status={delete_benign.status_code} "
                    f"body={delete_benign.text!r}"
                )
                return 1
            delete_benign_body = delete_benign.json()
            try:
                allowed = assert_bridge_semantic_delete(delete_benign_body)
            except AssertionError as exc:
                print(f"FAIL bridge delete home-path: {exc} body={delete_benign_body!r}")
                return 1
            outcome = "allowed=True (validated_only)" if allowed else "allowed=False (Guardian/domain block)"
            print(f"PASS bridge delete home-path semantic: {outcome}")

            delete_deny_floor = client.post(
                "/validate",
                json={
                    "action": "DELETE_HOST_FILE",
                    "path": "~/.ssh/intentframe-bridge-delete-deny-floor-probe",
                    "target": "~/.ssh/intentframe-bridge-delete-deny-floor-probe",
                    "reason": "Should be blocked by delete deny floor",
                },
            )
            if delete_deny_floor.status_code != 200:
                print(
                    f"FAIL bridge delete deny-floor: status={delete_deny_floor.status_code} "
                    f"body={delete_deny_floor.text!r}"
                )
                return 1
            delete_deny_floor_body = delete_deny_floor.json()
            if delete_deny_floor_body.get("allowed"):
                print(
                    f"FAIL bridge delete deny-floor: expected allowed=False "
                    f"body={delete_deny_floor_body!r}"
                )
                return 1
            print(f"PASS bridge delete deny-floor: error={delete_deny_floor_body.get('error')!r}")

            delete_blocked = client.post(
                "/validate",
                json={
                    "action": "DELETE_HOST_FILE",
                    "path": "/etc/sudoers",
                    "target": "/etc/sudoers",
                    "reason": "Should be blocked by delete floor",
                },
            )
            if delete_blocked.status_code != 200:
                print(
                    f"FAIL bridge delete blocked: status={delete_blocked.status_code} "
                    f"body={delete_blocked.text!r}"
                )
                return 1
            delete_blocked_body = delete_blocked.json()
            if delete_blocked_body.get("allowed"):
                print(
                    f"FAIL bridge delete blocked: expected allowed=False "
                    f"body={delete_blocked_body!r}"
                )
                return 1
            print(f"PASS bridge delete blocked: error={delete_blocked_body.get('error')!r}")

    return 0
