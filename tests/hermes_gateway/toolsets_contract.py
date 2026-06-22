"""Contract for GET /v1/toolsets after intentframe-gate integration.

Validates the Hermes api_server tool *name* surface the LLM can choose from.
Names only — full JSON schemas are probed separately via ``probe_hermes_tool_schemas.py``.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_TESTS_DIR = Path(__file__).resolve().parent.parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from hermes_governance_fixtures import template_enabled_tool_names  # noqa: E402

# Hermes 0.17 hermes-api-server composite (toolsets.py) — names the model may see.
API_SERVER_COMPOSITE_TOOLSET = "hermes-api-server"

# Governed tools in governance/tools.yaml that are not standalone Hermes 0.17 registry tools.
GOVERNED_TOOLS_NOT_ON_API_SERVER = frozenset({"delete_file"})


def governed_tools_on_api_server() -> frozenset[str]:
    return template_enabled_tool_names() - GOVERNED_TOOLS_NOT_ON_API_SERVER

# Ungoverned tools that explain LLM tool-selection noise in gateway E2E.
UNGATED_DISTRACTOR_TOOLS = frozenset(
    {"vision_analyze", "execute_code", "skill_manage"}
)

# Individual toolsets that must be enabled when api_server uses the default composite.
EXPECTED_ENABLED_TOOLSETS = frozenset(
    {
        "terminal",
        "file",
        "vision",
        "code_execution",
        "skills",
        "web",
        "browser",
        "todo",
        "memory",
        "session_search",
        "delegation",
        "cronjob",
        "image_gen",
    }
)

TOOLSET_TOOL_EXPECTATIONS: dict[str, frozenset[str]] = {
    "terminal": frozenset({"terminal", "process"}),
    "file": frozenset({"read_file", "write_file", "patch", "search_files"}),
    "vision": frozenset({"vision_analyze"}),
    "code_execution": frozenset({"execute_code"}),
    "skills": frozenset({"skills_list", "skill_view", "skill_manage"}),
}


@dataclass(frozen=True)
class ToolsetEntry:
    name: str
    enabled: bool
    configured: bool
    tools: tuple[str, ...]


@dataclass(frozen=True)
class ToolsetsSnapshot:
    platform: str
    entries: tuple[ToolsetEntry, ...]
    enabled_tool_names: frozenset[str]

    def by_name(self) -> dict[str, ToolsetEntry]:
        return {entry.name: entry for entry in self.entries}


def parse_toolsets_response(body: dict[str, Any]) -> ToolsetsSnapshot:
    if body.get("object") != "list":
        raise AssertionError(f"Expected toolsets object=list, got: {body.get('object')!r}")
    platform = body.get("platform")
    if platform != "api_server":
        raise AssertionError(f"Expected platform=api_server, got: {platform!r}")

    raw_data = body.get("data")
    if not isinstance(raw_data, list):
        raise AssertionError(f"Expected toolsets data list, got: {type(raw_data)!r}")

    entries: list[ToolsetEntry] = []
    enabled_names: set[str] = set()

    for item in raw_data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            continue
        tools_raw = item.get("tools")
        if not isinstance(tools_raw, list):
            tools = ()
        else:
            tools = tuple(sorted(str(t) for t in tools_raw if isinstance(t, str)))
        enabled = bool(item.get("enabled"))
        configured = bool(item.get("configured"))
        entries.append(
            ToolsetEntry(
                name=name,
                enabled=enabled,
                configured=configured,
                tools=tools,
            )
        )
        if enabled:
            enabled_names.update(tools)

    return ToolsetsSnapshot(
        platform=str(platform),
        entries=tuple(entries),
        enabled_tool_names=frozenset(enabled_names),
    )


def format_toolsets_snapshot(snapshot: ToolsetsSnapshot) -> str:
    lines = [
        f"platform={snapshot.platform}",
        f"enabled_tool_count={len(snapshot.enabled_tool_names)}",
        "",
        "enabled toolsets:",
    ]
    for entry in snapshot.entries:
        if not entry.enabled:
            continue
        lines.append(f"  {entry.name}: {list(entry.tools)}")
    lines.extend(
        [
            "",
            "union of enabled tool names:",
            f"  {sorted(snapshot.enabled_tool_names)}",
        ]
    )
    return "\n".join(lines)


def assert_intentframe_gate_toolsets_surface(body: dict[str, Any]) -> ToolsetsSnapshot:
    """Assert /v1/toolsets matches expectations after intentframe-gate is integrated."""
    snapshot = parse_toolsets_response(body)
    by_name = snapshot.by_name()

    missing_toolsets = sorted(EXPECTED_ENABLED_TOOLSETS - set(by_name))
    if missing_toolsets:
        raise AssertionError(
            f"Missing expected configurable toolsets: {missing_toolsets}"
        )

    for toolset_name, expected_tools in TOOLSET_TOOL_EXPECTATIONS.items():
        entry = by_name[toolset_name]
        if not entry.enabled:
            raise AssertionError(f"Expected toolset {toolset_name!r} to be enabled")
        actual = frozenset(entry.tools)
        if actual != expected_tools:
            raise AssertionError(
                f"Toolset {toolset_name!r} tools mismatch.\n"
                f"  expected: {sorted(expected_tools)}\n"
                f"  actual:   {sorted(actual)}"
            )

    missing_governed = sorted(governed_tools_on_api_server() - snapshot.enabled_tool_names)
    if missing_governed:
        raise AssertionError(
            f"Governed tools missing from enabled api_server surface: {missing_governed}"
        )

    missing_distractors = sorted(UNGATED_DISTRACTOR_TOOLS - snapshot.enabled_tool_names)
    if missing_distractors:
        raise AssertionError(
            f"Expected ungoverned distractor tools on api_server surface "
            f"(LLM may pick these instead of terminal): {missing_distractors}"
        )

    unexpected_governed_missing = sorted(
        template_enabled_tool_names()
        - governed_tools_on_api_server()
        - GOVERNED_TOOLS_NOT_ON_API_SERVER
    )
    if unexpected_governed_missing:
        raise AssertionError(
            f"template_enabled_tool_names includes tools not classified for api_server: "
            f"{unexpected_governed_missing}"
        )

    return snapshot


def toolsets_response_to_json(body: dict[str, Any]) -> str:
    return json.dumps(body, indent=2, sort_keys=True)
