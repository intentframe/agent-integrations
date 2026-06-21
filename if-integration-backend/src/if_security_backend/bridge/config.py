"""Bridge agent registry (secret → IntentFrame identity)."""

from __future__ import annotations

import os
import secrets
from dataclasses import dataclass
from pathlib import Path

import yaml


class BridgeConfigError(ValueError):
    """Invalid or missing bridge configuration."""


@dataclass(frozen=True)
class BridgeAgentConfig:
    agent_id: str
    secret: str
    user_id: str
    agent_type: str
    action_types: tuple[str, ...]


def bridge_config_path() -> Path:
    override = os.environ.get("INTENTFRAME_BRIDGE_CONFIG")
    if override:
        return Path(override).expanduser()
    from if_security_backend.runtime.paths import state_dir

    persisted = state_dir() / "bridge_agent_config"
    if persisted.is_file():
        try:
            return Path(persisted.read_text(encoding="utf-8").strip()).expanduser()
        except OSError:
            pass
    from if_security_backend.agent_config import default_test_agent_pack_path

    return default_test_agent_pack_path()


def persist_bridge_config_path(path: Path) -> None:
    from if_security_backend.runtime.paths import state_dir

    state_dir().mkdir(parents=True, exist_ok=True)
    (state_dir() / "bridge_agent_config").write_text(str(path.expanduser().resolve()), encoding="utf-8")


def load_bridge_agents_yaml(path: Path) -> tuple[str | None, dict[str, BridgeAgentConfig]]:
    """Parse multi-agent YAML registry."""
    if not path.is_file():
        raise BridgeConfigError(f"Bridge config not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise BridgeConfigError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise BridgeConfigError(f"Bridge config must be a mapping: {path}")

    default_user = raw.get("default_user_id")
    if default_user is not None and not isinstance(default_user, str):
        raise BridgeConfigError("default_user_id must be a string")

    agents_raw = raw.get("agents")
    if not isinstance(agents_raw, dict) or not agents_raw:
        raise BridgeConfigError("YAML bridge config must define a non-empty agents: mapping")

    env_user = os.environ.get("INTENTFRAME_USER_ID")
    agents: dict[str, BridgeAgentConfig] = {}

    for agent_id, entry in agents_raw.items():
        if not isinstance(agent_id, str) or not isinstance(entry, dict):
            raise BridgeConfigError(f"Invalid agents.{agent_id!r} entry")

        secret = entry.get("secret") or entry.get("bridge_secret")
        if not isinstance(secret, str) or not secret.strip():
            raise BridgeConfigError(f"agents.{agent_id}.secret is required")

        user_id = entry.get("user_id") or default_user or env_user
        if not user_id:
            raise BridgeConfigError(
                f"agents.{agent_id}.user_id missing and no default_user_id / INTENTFRAME_USER_ID"
            )

        action_types = entry.get("action_types") or ["RUN_COMMAND"]
        if not isinstance(action_types, list) or not action_types:
            raise BridgeConfigError(f"agents.{agent_id}.action_types must be a non-empty list")

        agent_type = entry.get("agent_type") or agent_id

        agents[agent_id] = BridgeAgentConfig(
            agent_id=agent_id,
            secret=secret.strip(),
            user_id=str(user_id),
            agent_type=str(agent_type),
            action_types=tuple(str(a) for a in action_types),
        )

    return (default_user, agents)


def load_bridge_agents(config_path: Path | None = None) -> dict[str, BridgeAgentConfig]:
    from if_security_backend.agent_config import load_bridge_agents_from_path

    path = config_path or bridge_config_path()
    return load_bridge_agents_from_path(path)


def resolve_agent_by_secret(
    token: str,
    agents: dict[str, BridgeAgentConfig],
) -> BridgeAgentConfig | None:
    for agent in agents.values():
        if secrets.compare_digest(token, agent.secret):
            return agent
    return None
