"""Integration pack metadata (agent profile + optional adapter sidecar)."""

from __future__ import annotations

import json
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
    agent = load_agent_pack(path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    adapter = _parse_adapter(raw.get("adapter"), base_dir=path.parent)
    return IntegrationPack(agent=agent, adapter=adapter)
