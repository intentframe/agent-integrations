"""Load governed-tool contract from runtime or bundled default YAML."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

VALID_BLOCKED_RESPONSES = frozenset({"terminal_json", "generic_json"})
VALID_MAPPER_KINDS = frozenset({"terminal", "process", "write_file", "patch", "generic"})
BUILTIN_MODULE_PREFIX = "tools."


@dataclass(frozen=True)
class ToolSpec:
    name: str
    action: str
    risk: str
    mapper: str
    blocked_response: str = "generic_json"
    actions: tuple[str, ...] = ()
    enabled: bool = True
    builtin_module: str | None = None

    def policy_actions(self) -> frozenset[str]:
        if self.actions:
            return frozenset(self.actions)
        return frozenset({self.action})


def _runtime_governance_path() -> Path | None:
    candidate = (
        Path.home()
        / ".intentframe"
        / "integrations"
        / "hermes"
        / "governance"
        / "tools.yaml"
    )
    if candidate.is_file():
        return candidate
    return None


def _resolve_yaml_path(explicit: Path | None = None) -> Path:
    if explicit is not None:
        path = explicit.expanduser()
        if not path.is_file():
            raise FileNotFoundError(f"Governance YAML not found: {path}")
        return path

    env_path = os.environ.get("HERMES_GOVERNANCE_YAML", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"Governance YAML not found (HERMES_GOVERNANCE_YAML): {path}"
            )
        return path

    runtime_path = _runtime_governance_path()
    if runtime_path is not None:
        return runtime_path

    bundled = resources.files("hermes_governance").joinpath("tools.yaml")
    with resources.as_file(bundled) as path:
        if path.is_file():
            return path

    raise FileNotFoundError("Could not locate Hermes governance tools.yaml")


def _parse_actions(raw: dict[str, Any], primary_action: str) -> tuple[str, ...]:
    extra = raw.get("actions")
    if extra is None:
        return ()
    if not isinstance(extra, list | tuple) or not extra:
        raise ValueError("actions must be a non-empty list when present")
    parsed = tuple(str(action).strip() for action in extra)
    if not all(parsed):
        raise ValueError("actions must contain non-empty strings")
    if primary_action not in parsed:
        raise ValueError("actions must include the primary action field")
    return parsed


def _parse_enabled(raw: dict[str, Any]) -> bool:
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean when present")
    return enabled


def _parse_builtin_module(name: str, raw: dict[str, Any]) -> str | None:
    value = raw.get("builtin_module")
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Tool {name!r} builtin_module must be a non-empty string when present")
    module = value.strip()
    if not module.startswith(BUILTIN_MODULE_PREFIX):
        raise ValueError(
            f"Tool {name!r} builtin_module {module!r} must start with {BUILTIN_MODULE_PREFIX!r}"
        )
    return module


def _parse_tool(name: str, raw: dict[str, Any]) -> ToolSpec:
    if not isinstance(raw, dict):
        raise ValueError(f"Tool {name!r} must be a mapping")

    action = raw.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError(f"Tool {name!r} missing non-empty action")

    risk = raw.get("risk")
    if not isinstance(risk, str) or not risk.strip():
        raise ValueError(f"Tool {name!r} missing non-empty risk")

    mapper = raw.get("mapper")
    if not isinstance(mapper, str) or mapper not in VALID_MAPPER_KINDS:
        raise ValueError(
            f"Tool {name!r} has invalid mapper {mapper!r}; "
            f"expected one of {sorted(VALID_MAPPER_KINDS)}"
        )

    blocked_response = raw.get("blocked_response", "generic_json")
    if blocked_response not in VALID_BLOCKED_RESPONSES:
        raise ValueError(
            f"Tool {name!r} has invalid blocked_response {blocked_response!r}; "
            f"expected one of {sorted(VALID_BLOCKED_RESPONSES)}"
        )

    primary_action = action.strip()
    return ToolSpec(
        name=name,
        action=primary_action,
        risk=risk.strip(),
        mapper=mapper,
        blocked_response=blocked_response,
        actions=_parse_actions(raw, primary_action),
        enabled=_parse_enabled(raw),
        builtin_module=_parse_builtin_module(name, raw),
    )


@lru_cache(maxsize=4)
def load_tool_catalog(yaml_path: str | None = None) -> dict[str, ToolSpec]:
    """All tools defined in governance YAML (enabled and disabled)."""
    path = _resolve_yaml_path(Path(yaml_path) if yaml_path else None)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tools_raw = raw.get("tools")
    if not isinstance(tools_raw, dict) or not tools_raw:
        raise ValueError(f"Governance YAML must contain non-empty tools mapping: {path}")

    tools: dict[str, ToolSpec] = {}
    for name, spec_raw in tools_raw.items():
        if not isinstance(name, str) or not name.strip():
            raise ValueError("Tool names must be non-empty strings")
        if name in tools:
            raise ValueError(f"Duplicate governed tool name: {name!r}")
        tools[name] = _parse_tool(name, spec_raw)
    return tools


def load_governed_tools(yaml_path: str | None = None) -> dict[str, ToolSpec]:
    """IntentFrame-governed tools only (yaml ``enabled: true``).

    Runtime governed set for plugin and adapter. Not Hermes /v1/toolsets enablement.
    """
    catalog = load_tool_catalog(yaml_path)
    enabled = {name: spec for name, spec in catalog.items() if spec.enabled}
    if not enabled:
        raise ValueError("Governance YAML must have at least one enabled tool")
    return enabled


def governance_catalog_names() -> frozenset[str]:
    return frozenset(load_tool_catalog())


def governed_tool_names() -> frozenset[str]:
    return frozenset(load_governed_tools())


def supported_tools() -> dict[str, str]:
    return {name: spec.action for name, spec in load_governed_tools().items()}


def supported_actions() -> frozenset[str]:
    actions: set[str] = set()
    for spec in load_governed_tools().values():
        actions.update(spec.policy_actions())
    return frozenset(actions)


def generic_mapper_action_ids(yaml_path: str | None = None) -> frozenset[str]:
    """Action IDs for enabled tools using mapper: generic."""
    tools = load_governed_tools(yaml_path)
    return frozenset(spec.action for spec in tools.values() if spec.mapper == "generic")
