"""Enable/disable governed Hermes tools in runtime governance/tools.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from intentframe_integrations.hermes_governance_contract import (
    HERMES_AGENT_ID,
    ensure_runtime_governance_yaml,
)


class GovernanceEditError(Exception):
    pass


def active_governance_yaml_path(agent_id: str = HERMES_AGENT_ID) -> Path:
    """Runtime user config under ~/.intentframe/integrations/<agent>/governance/."""
    return ensure_runtime_governance_yaml(agent_id)


def _resolve_yaml_path(
    agent_id: str,
    yaml_path: Path | None,
) -> Path:
    if yaml_path is not None:
        path = yaml_path.expanduser()
        if not path.is_file():
            raise GovernanceEditError(f"Governance yaml not found: {path}")
        return path
    return active_governance_yaml_path(agent_id)


def _load_tools_mapping(path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise GovernanceEditError(f"Governance yaml must be a mapping: {path}")
    tools = raw.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise GovernanceEditError(f"Governance yaml must contain non-empty tools mapping: {path}")
    return raw, tools


def list_governed_tools(
    agent_id: str = HERMES_AGENT_ID,
    *,
    yaml_path: Path | None = None,
) -> list[tuple[str, bool]]:
    path = _resolve_yaml_path(agent_id, yaml_path)
    _, tools = _load_tools_mapping(path)
    result: list[tuple[str, bool]] = []
    for name, spec in tools.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            continue
        enabled = spec.get("enabled", True)
        if not isinstance(enabled, bool):
            raise GovernanceEditError(f"Tool {name!r} has non-boolean enabled field")
        result.append((name, enabled))
    return result


def _count_enabled(tools: dict[str, Any]) -> int:
    count = 0
    for name, spec in tools.items():
        if not isinstance(spec, dict):
            continue
        if spec.get("enabled", True):
            count += 1
    return count


def set_tool_enabled(
    tool: str,
    enabled: bool,
    *,
    agent_id: str = HERMES_AGENT_ID,
    yaml_path: Path | None = None,
) -> Path:
    path = _resolve_yaml_path(agent_id, yaml_path)
    raw, tools = _load_tools_mapping(path)

    if tool not in tools:
        known = ", ".join(sorted(str(name) for name in tools))
        raise GovernanceEditError(f"Unknown governed tool {tool!r} (known: {known})")

    spec = tools[tool]
    if not isinstance(spec, dict):
        raise GovernanceEditError(f"Tool {tool!r} must be a mapping")

    current = spec.get("enabled", True)
    if not isinstance(current, bool):
        raise GovernanceEditError(f"Tool {tool!r} has non-boolean enabled field")

    if current == enabled:
        return path

    if not enabled and _count_enabled(tools) <= 1:
        raise GovernanceEditError(
            f"Cannot disable {tool!r}: at least one governed tool must remain enabled"
        )

    spec["enabled"] = enabled
    path.write_text(
        yaml.safe_dump(raw, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return path


def runtime_governed_tool_names(
    agent_id: str = HERMES_AGENT_ID,
    *,
    yaml_path: Path | None = None,
) -> list[str]:
    return [name for name, enabled in list_governed_tools(agent_id, yaml_path=yaml_path) if enabled]
