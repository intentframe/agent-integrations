"""Load per-agent JSON packs (policy path, bridge secret, exported env)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from if_security_backend.bridge.config import BridgeAgentConfig, BridgeConfigError


@dataclass(frozen=True)
class AgentPack:
    """One agent's policy + bridge identity + env exports for clients."""

    agent_id: str
    user_id: str
    bridge_secret: str
    agent_type: str
    action_types: tuple[str, ...]
    policy_file: Path | None
    env: dict[str, str]
    source_path: Path

    def bridge_agent(self) -> BridgeAgentConfig:
        return BridgeAgentConfig(
            agent_id=self.agent_id,
            secret=self.bridge_secret,
            user_id=self.user_id,
            agent_type=self.agent_type,
            action_types=self.action_types,
        )


from if_security_backend.runtime.paths import bundled_config


def bundled_agent_dir(name: str) -> Path:
    return bundled_config("agents", name)


def default_test_agent_pack_path() -> Path:
    return bundled_agent_dir("default") / "agent.json"


def default_test_policy_path() -> Path:
    return bundled_agent_dir("default") / "policy.yaml"


def _resolve_policy_file(raw: object, base_dir: Path) -> Path | None:
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = Path(raw.strip())
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def load_agent_pack(path: Path) -> AgentPack:
    if not path.is_file():
        raise BridgeConfigError(f"Agent config not found: {path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise BridgeConfigError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise BridgeConfigError(f"Agent config must be a JSON object: {path}")

    agent_id = raw.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise BridgeConfigError("agent_id is required")

    secret = raw.get("bridge_secret") or raw.get("secret")
    if not isinstance(secret, str) or not secret.strip():
        raise BridgeConfigError("bridge_secret is required")

    user_id = raw.get("user_id") or os.environ.get("INTENTFRAME_USER_ID")
    if not user_id:
        raise BridgeConfigError("user_id required in JSON or INTENTFRAME_USER_ID")

    action_types = raw.get("action_types") or ["RUN_COMMAND"]
    if not isinstance(action_types, list) or not action_types:
        raise BridgeConfigError("action_types must be a non-empty list")

    agent_type = str(raw.get("agent_type") or agent_id)
    base_dir = path.parent
    policy_file = _resolve_policy_file(raw.get("policy_file"), base_dir)

    env_raw = raw.get("env") or {}
    if not isinstance(env_raw, dict):
        raise BridgeConfigError("env must be an object of string keys/values")
    env = {str(k): str(v) for k, v in env_raw.items()}

    return AgentPack(
        agent_id=agent_id.strip(),
        user_id=str(user_id),
        bridge_secret=secret.strip(),
        agent_type=agent_type,
        action_types=tuple(str(a) for a in action_types),
        policy_file=policy_file,
        env=env,
        source_path=path.resolve(),
    )


def load_bridge_agents_from_path(path: Path) -> dict[str, BridgeAgentConfig]:
    """Load one agent JSON, a multi-agent YAML registry, or every *.json in a directory."""
    if path.is_dir():
        agents: dict[str, BridgeAgentConfig] = {}
        for child in sorted(path.rglob("agent.json")):
            agents.update(load_bridge_agents_from_path(child))
        if not agents:
            raise BridgeConfigError(f"No agent.json files under directory: {path}")
        return agents

    if path.suffix.lower() == ".json":
        pack = load_agent_pack(path)
        agent = pack.bridge_agent()
        return {agent.agent_id: agent}

    from if_security_backend.bridge.config import load_bridge_agents_yaml

    _, agents = load_bridge_agents_yaml(path)
    return agents
