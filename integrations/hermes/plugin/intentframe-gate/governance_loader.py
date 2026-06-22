"""Load governed-tool contract for the Hermes plugin (no adapter dependency)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

VALID_BLOCKED_RESPONSES = frozenset({"terminal_json", "generic_json"})
VALID_MAPPER_KINDS = frozenset({"terminal", "process", "write_file", "delete_file", "patch"})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    action: str
    risk: str
    mapper: str
    blocked_response: str = "generic_json"
    actions: tuple[str, ...] = ()

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


def _repo_governance_path() -> Path | None:
    here = Path(__file__).resolve().parent
    candidate = here.parents[1] / "governance" / "tools.yaml"
    if candidate.is_file():
        return candidate
    return None


def _resolve_yaml_path() -> Path:
    env_path = os.environ.get("HERMES_GOVERNANCE_YAML", "").strip()
    if env_path:
        path = Path(env_path).expanduser()
        if path.is_file():
            return path

    repo = _repo_governance_path()
    if repo is not None:
        return repo

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
    )


@lru_cache(maxsize=1)
def load_governed_tools() -> dict[str, ToolSpec]:
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


def governed_tool_names() -> frozenset[str]:
    return frozenset(load_governed_tools())
