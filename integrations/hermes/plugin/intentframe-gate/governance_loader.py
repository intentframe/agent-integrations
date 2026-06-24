"""Load governed-tool contract for the Hermes plugin (no adapter dependency)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

VALID_BLOCKED_RESPONSES = frozenset({"terminal_json", "generic_json"})
VALID_MAPPER_KINDS = frozenset({"terminal", "write_file", "patch", "generic", "execute_code"})
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


def _resolve_yaml_path() -> Path:
    env_path = os.environ.get("HERMES_GOVERNANCE_YAML", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if not path.is_file():
            raise FileNotFoundError(
                f"Governance YAML not found (HERMES_GOVERNANCE_YAML): {path}"
            )
        return path

    runtime = _runtime_governance_path()
    if runtime is not None:
        return runtime

    raise FileNotFoundError(
        "Could not locate Hermes governance tools.yaml "
        "(set HERMES_GOVERNANCE_YAML or run intentframe-integrations integrate hermes)"
    )


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
    action = str(raw.get("action", "")).strip()
    risk = str(raw.get("risk", "")).strip()
    mapper = str(raw.get("mapper", "")).strip()
    blocked_response = raw.get("blocked_response", "generic_json")
    if not action or not risk or not mapper:
        raise ValueError(f"Invalid governed tool spec for {name!r}")
    if mapper not in VALID_MAPPER_KINDS:
        raise ValueError(f"Invalid mapper for {name!r}")
    if blocked_response not in VALID_BLOCKED_RESPONSES:
        raise ValueError(f"Invalid blocked_response for {name!r}")
    return ToolSpec(
        name=name,
        action=action,
        risk=risk,
        mapper=mapper,
        blocked_response=blocked_response,
        actions=_parse_actions(raw, action),
        enabled=_parse_enabled(raw),
        builtin_module=_parse_builtin_module(name, raw),
    )


@lru_cache(maxsize=1)
def load_tool_catalog() -> dict[str, ToolSpec]:
    """All tools defined in governance YAML (enabled and disabled)."""
    path = _resolve_yaml_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tools_raw = raw.get("tools")
    if not isinstance(tools_raw, dict) or not tools_raw:
        raise ValueError(f"Governance YAML must contain tools mapping: {path}")
    return {
        name: _parse_tool(name, spec_raw)
        for name, spec_raw in tools_raw.items()
        if isinstance(name, str)
    }


def load_governed_tools() -> dict[str, ToolSpec]:
    """IntentFrame-governed tools only (yaml ``enabled: true``).

    Runtime governed set for plugin wrap. Not Hermes toolset enablement.
    """
    catalog = load_tool_catalog()
    enabled = {name: spec for name, spec in catalog.items() if spec.enabled}
    if not enabled:
        raise ValueError("Governance YAML must have at least one enabled tool")
    return enabled


def governed_tool_names() -> frozenset[str]:
    return frozenset(load_governed_tools())
