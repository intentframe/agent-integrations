"""Direct Actor → IntentFrame core integration tests."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from intentframe_actor import Actor
from intentframe_core.types import AgentCapabilities

from if_security_backend.agent_config import default_test_agent_pack_path, load_agent_pack
from if_security_backend.runtime.health import core_healthy


def run_core_connection_tests(agent_config: Path | None = None) -> int:
    if not core_healthy():
        print("Core is not healthy — run: if-integration-backend start", file=sys.stderr)
        return 1

    pack = load_agent_pack(agent_config or default_test_agent_pack_path())
    os.environ.setdefault("INTENTFRAME_USER_ID", pack.user_id)
    os.environ.setdefault("INTENTFRAME_AGENT_ID", pack.agent_id)

    async def _submit(command: str, reason: str):
        actor = Actor(agent_id=pack.agent_id, user_id=pack.user_id)
        caps = AgentCapabilities(
            agent_type=pack.agent_type,
            description=f"Core connection test for {pack.agent_id}",
            action_types=list(pack.action_types),
        )
        await actor.handshake(caps)
        result = await actor.submit(
            {
                "action": "RUN_COMMAND",
                "command": command,
                "target": command[:200],
                "reason": reason,
            }
        )
        await actor.close()
        data = result.data if isinstance(result.data, dict) else {}
        return result.success, data, result.error

    async def _run() -> int:
        ok, data, err = await _submit("echo if-backend-core-ok", "Core connection benign")
        if not ok:
            print(f"FAIL core benign: success=False error={err!r} data={data!r}")
            return 1
        if not data.get("validated_only"):
            print(f"FAIL core benign: expected validated_only=True data={data!r}")
            return 1
        print(f"PASS core benign: validated_only={data.get('validated_only')}")

        blocked_ok, blocked_data, blocked_err = await _submit(
            "sudo rm -rf /",
            "Should be blocked",
        )
        if blocked_ok:
            print(f"FAIL core blocked: expected success=False data={blocked_data!r}")
            return 1
        print(f"PASS core blocked: error={blocked_err!r}")
        return 0

    return asyncio.run(_run())
