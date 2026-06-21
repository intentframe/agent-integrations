"""Runtime ownership checks and coordinated backend/adapter startup."""

from __future__ import annotations

import secrets
from pathlib import Path

from if_security_backend.bridge.config import bridge_config_path, load_bridge_agents
from if_security_backend.bridge.runner import is_bridge_running, start_bridge
from if_security_backend.runtime.health import core_healthy

from intentframe_integrations.integration_pack import IntegrationPack


def bridge_serves_pack(pack: IntegrationPack) -> bool:
    """Return True when the running bridge is configured for this agent pack."""
    if not is_bridge_running():
        return False
    try:
        agents = load_bridge_agents(bridge_config_path())
    except (OSError, ValueError):
        return False

    agent = pack.agent
    cfg = agents.get(agent.agent_id)
    if cfg is None:
        return False
    return secrets.compare_digest(cfg.secret, agent.bridge_secret)


def backend_ready_for_pack(pack: IntegrationPack) -> bool:
    return core_healthy() and is_bridge_running() and bridge_serves_pack(pack)


def ensure_backend_for_pack(
    pack: IntegrationPack,
    *,
    run_backend_start,
) -> tuple[bool, str | None, bool]:
    """Ensure core + bridge serve ``pack``.

    Returns ``(ok, error_message, started_backend_this_call)``.
    ``run_backend_start`` is injected for tests (typically ``backend_main(["start", ...])``).
    """
    if backend_ready_for_pack(pack):
        return True, None, False

    if core_healthy() and is_bridge_running() and not bridge_serves_pack(pack):
        persisted = bridge_config_path()
        return (
            False,
            (
                f"IntentFrame runtime is up but bridge config does not match "
                f"agent {pack.agent.agent_id!r} ({persisted}). "
                "Run: intentframe-integrations stop && "
                f"intentframe-integrations start {pack.agent.agent_id}"
            ),
            False,
        )

    if core_healthy() and not is_bridge_running():
        from if_security_backend.bridge.config import persist_bridge_config_path
        from if_security_backend.bridge.runner import BridgeError

        cfg = pack.agent.source_path
        persist_bridge_config_path(cfg)
        try:
            start_bridge(detach=True, config_path=cfg)
        except BridgeError as exc:
            return False, str(exc), False
        if not bridge_serves_pack(pack):
            return False, "Bridge started but agent is not registered", False
        return True, None, False

    ec = run_backend_start(["start", "--agent-config", str(pack.agent.source_path)])
    if ec:
        return False, "IntentFrame backend failed to start", False
    if not backend_ready_for_pack(pack):
        return False, "Backend started but bridge is not ready for this agent", True
    return True, None, True


def iter_agent_configs(path: Path) -> list[Path]:
    """Return agent.json paths from a file or directory."""
    resolved = path.expanduser().resolve()
    if resolved.is_file():
        return [resolved]
    if resolved.is_dir():
        return sorted(resolved.rglob("agent.json"))
    return []
