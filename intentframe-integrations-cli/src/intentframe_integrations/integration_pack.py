"""Integration pack metadata (agent profile + optional adapter sidecar).

Pack activation (``load_and_activate_pack*``) is the single entrypoint for CLI
commands that need agent env + Hermes runtime artifacts before backend boot or
in-process policy validation. Precedence: explicit ``os.environ`` → ``agent.json``
``env`` (``setdefault``) → seeded files under ``~/.intentframe/integrations/``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from if_security_backend.agent_config import AgentPack, load_agent_pack
from if_security_backend.bridge.config import BridgeConfigError


@dataclass(frozen=True)
class AdapterSpec:
    """Sidecar adapter configuration from agent.json."""

    runtime: str
    socket: str
    source_dir: Path
    python: str
    module: str

    def socket_path(self) -> Path:
        return Path(self.socket).expanduser()


@dataclass(frozen=True)
class IntegrationPack:
    agent: AgentPack
    adapter: AdapterSpec | None


def _parse_adapter(raw: object, *, base_dir: Path) -> AdapterSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise BridgeConfigError("adapter must be an object")

    runtime = raw.get("runtime")
    if not isinstance(runtime, str) or not runtime.strip():
        raise BridgeConfigError("adapter.runtime is required")

    socket = raw.get("socket")
    if not isinstance(socket, str) or not socket.strip():
        raise BridgeConfigError("adapter.socket is required")

    source = raw.get("source", "adapter")
    if not isinstance(source, str) or not source.strip():
        raise BridgeConfigError("adapter.source must be a non-empty string")

    source_dir = Path(source.strip())
    if not source_dir.is_absolute():
        source_dir = (base_dir / source_dir).resolve()

    python = raw.get("python", "3.12")
    if not isinstance(python, str) or not python.strip():
        raise BridgeConfigError("adapter.python must be a non-empty string")

    module = raw.get("module", "hermes_adapter.main")
    if not isinstance(module, str) or not module.strip():
        raise BridgeConfigError("adapter.module must be a non-empty string")

    return AdapterSpec(
        runtime=runtime.strip(),
        socket=socket.strip(),
        source_dir=source_dir,
        python=python.strip(),
        module=module.strip(),
    )


def load_integration_pack(path: Path) -> IntegrationPack:
    """Parse agent.json only — no env side effects. Prefer ``load_and_activate_pack*``."""
    agent = load_agent_pack(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    adapter = _parse_adapter(raw.get("adapter"), base_dir=path.parent)
    return IntegrationPack(agent=agent, adapter=adapter)


def apply_agent_env(pack: IntegrationPack) -> None:
    """Apply agent.json env defaults; explicit os.environ values always win (setdefault)."""
    os.environ.setdefault("INTENTFRAME_USER_ID", pack.agent.user_id)
    os.environ.setdefault("INTENTFRAME_AGENT_ID", pack.agent.agent_id)
    for key, value in pack.agent.env.items():
        os.environ.setdefault(key, os.path.expanduser(value))


def seed_hermes_runtime_governance(pack: IntegrationPack) -> None:
    """Seed Hermes runtime governance artifacts before backend boot or validation.

    Ensures tools.yaml and generic_actions.manifest exist at their runtime paths
    so IF_DYNAMIC_BUNDLE_MANIFEST and HERMES_GOVERNANCE_YAML are never set to
    missing files. Safe to call before ``integrate hermes`` has run; if the
    committed templates are missing the error surfaces at integrate time.
    """
    from intentframe_integrations.hermes_governance_contract import (
        HERMES_AGENT_ID,
        ensure_runtime_actions_manifest,
        ensure_runtime_governance_yaml,
    )

    if pack.agent.agent_id != HERMES_AGENT_ID:
        return
    try:
        ensure_runtime_governance_yaml(HERMES_AGENT_ID)
        ensure_runtime_actions_manifest(HERMES_AGENT_ID)
    except FileNotFoundError:
        pass


def load_and_activate_pack_from_path(path: Path) -> IntegrationPack:
    """Load pack, apply agent env defaults, and seed Hermes runtime artifacts.

    Call before backend start or ``validate_policy_with_bundles`` so
    ``IF_DYNAMIC_BUNDLE_MANIFEST`` (generic ``HERMES_*`` actions) matches boot.
    """
    pack = load_integration_pack(path)
    apply_agent_env(pack)
    seed_hermes_runtime_governance(pack)
    return pack


def load_and_activate_pack(agent: str) -> IntegrationPack:
    """Load named agent pack and activate its runtime environment (see ``load_and_activate_pack_from_path``)."""
    from intentframe_integrations.paths import agent_config_path

    return load_and_activate_pack_from_path(agent_config_path(agent))
