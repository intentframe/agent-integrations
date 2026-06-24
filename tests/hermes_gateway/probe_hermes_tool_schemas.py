#!/usr/bin/env python3
"""Probe Hermes registry schemas after intentframe-gate (reason injection).

Run inside the managed Hermes venv with HERMES_HOME set. Used by gateway
toolsets live test to verify **all** IntentFrame-governed tools (native and
generic mappers) use Hermes names, require ``reason`` in their JSON schema,
and have gated handlers.

Requires ``HERMES_GATEWAY_SESSION=1`` in the probe environment (set by the
toolsets live harness) so ``cronjob`` passes Hermes ``check_fn`` filtering.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = REPO_ROOT / "tests"
PLUGIN_SRC = REPO_ROOT / "integrations" / "hermes" / "plugin" / "intentframe-gate"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))
if str(PLUGIN_SRC) not in sys.path:
    sys.path.insert(0, str(PLUGIN_SRC))

from governance_loader import governed_tool_names  # type: ignore  # noqa: E402


def main() -> int:
    hermes_home = os.environ.get("HERMES_HOME", "").strip()
    if not hermes_home:
        print("ERROR: HERMES_HOME not set", file=sys.stderr)
        return 1

    # Load Hermes builtins + plugins (intentframe-gate must be in config).
    from hermes_cli.plugins import PluginManager

    PluginManager().discover_and_load()

    from hermes_cli.config import load_config
    from hermes_cli.tools_config import _get_platform_tools
    from model_tools import get_tool_definitions
    from tools.registry import registry

    config = load_config()
    enabled_toolsets = _get_platform_tools(
        config,
        "api_server",
        include_default_mcp_servers=False,
    )
    definitions = get_tool_definitions(enabled_toolsets=enabled_toolsets, quiet_mode=True)

    probe_targets = governed_tool_names()
    by_name: dict[str, dict] = {}
    for item in definitions:
        fn = item.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if isinstance(name, str):
            by_name[name] = fn

    report: dict[str, object] = {
        "hermes_home": hermes_home,
        "enabled_toolset_count": len(enabled_toolsets),
        "definition_count": len(definitions),
        "governed_tools": {},
        "distractors": {},
    }

    errors: list[str] = []

    for tool_name in sorted(probe_targets):
        if tool_name not in by_name:
            errors.append(f"governed tool {tool_name!r} missing from get_tool_definitions()")
            continue

        params = by_name[tool_name].get("parameters") or {}
        required = params.get("required") or []
        has_reason = "reason" in (params.get("properties") or {})
        reason_required = "reason" in required
        entry = registry.get_entry(tool_name)
        gated = bool(entry and getattr(entry.handler, "__intentframe_gated__", False))

        report["governed_tools"][tool_name] = {
            "present": True,
            "reason_in_schema": has_reason,
            "reason_required": reason_required,
            "handler_gated": gated,
            "required": list(required),
        }
        if not has_reason or not reason_required:
            errors.append(f"{tool_name}: expected reason in required schema fields")
        if entry and not gated:
            errors.append(f"{tool_name}: registry handler missing intentframe gate marker")

    for distractor in ("vision_analyze", "skill_manage"):
        fn = by_name.get(distractor)
        if fn is None:
            errors.append(f"expected distractor {distractor!r} on api_server surface")
            continue
        params = fn.get("parameters") or {}
        props = params.get("properties") or {}
        required = params.get("required") or []
        report["distractors"][distractor] = {
            "present": True,
            "reason_in_schema": "reason" in props,
            "reason_required": "reason" in required,
        }
        if "reason" in required:
            errors.append(f"{distractor}: should not require reason (ungoverned)")

    print(json.dumps(report, indent=2, sort_keys=True))

    if errors:
        print("ERRORS:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
