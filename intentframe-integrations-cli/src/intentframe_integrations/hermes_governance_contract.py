"""Default governance template paths and runtime user config materialization.

Repo templates (dev-maintained): governance/tools.yaml, governance/generic_actions.manifest.
Runtime copies (~/.intentframe/...): seeded on first integrate; never overwritten
unless the user runs --reset-governance or deletes the file. User toggles tool
governance via CLI; that only edits runtime tools.yaml enabled flags.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from intentframe_integrations.paths import repo_root

HERMES_AGENT_ID = "hermes"
DEFAULT_GOVERNANCE_TEMPLATE_RELATIVE = Path("integrations") / "hermes" / "governance" / "tools.yaml"
DEFAULT_GENERIC_ACTIONS_MANIFEST_RELATIVE = (
    Path("integrations") / "hermes" / "governance" / "generic_actions.manifest"
)


def default_governance_template_path() -> Path:
    """Default tools.yaml shipped with the repo (reference template only)."""
    return repo_root() / DEFAULT_GOVERNANCE_TEMPLATE_RELATIVE


def default_actions_manifest_template_path() -> Path:
    """Committed generic_actions.manifest shipped with the repo (dev-generated, static).

    Holds the full catalog of generic-mapper action IDs (enabled or not). It is a
    superset that never changes when a user toggles tool governance — only when a
    developer adds a tool to the catalog and regenerates it.
    """
    return repo_root() / DEFAULT_GENERIC_ACTIONS_MANIFEST_RELATIVE


def catalog_generic_action_ids() -> frozenset[str]:
    """All generic-mapper action IDs in the default catalog (ignores enabled)."""
    template = default_governance_template_path()
    if not template.is_file():
        raise FileNotFoundError(f"Default governance template missing: {template}")
    raw = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
    tools = raw.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise ValueError(f"Default governance template has no tools mapping: {template}")
    actions: set[str] = set()
    for spec in tools.values():
        if not isinstance(spec, dict):
            continue
        if spec.get("mapper") != "generic":
            continue
        action = str(spec.get("action", "")).strip()
        if action:
            actions.add(action)
    return frozenset(actions)


def format_manifest(action_ids: frozenset[str]) -> str:
    """Canonical manifest serialization (comma-separated, sorted)."""
    return ", ".join(sorted(action_ids))


def actions_manifest_runtime_path(agent_id: str = HERMES_AGENT_ID) -> Path:
    """User-runtime manifest path (copied from the committed template on install)."""
    return governance_yaml_runtime_path(agent_id).parent / "generic_actions.manifest"


def ensure_runtime_actions_manifest(agent_id: str = HERMES_AGENT_ID) -> Path:
    """Return runtime manifest, copying the committed template on first use only."""
    runtime = actions_manifest_runtime_path(agent_id)
    if runtime.is_file():
        return runtime

    template = default_actions_manifest_template_path()
    if not template.is_file():
        raise FileNotFoundError(
            f"Runtime actions manifest missing at {runtime} and no committed "
            f"template at {template}"
        )

    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, runtime)
    return runtime


def governance_yaml_runtime_path(agent_id: str = HERMES_AGENT_ID) -> Path:
    """User-owned runtime config edited by the CLI."""
    return (
        Path.home()
        / ".intentframe"
        / "integrations"
        / agent_id
        / "governance"
        / "tools.yaml"
    )


def ensure_runtime_governance_yaml(agent_id: str = HERMES_AGENT_ID) -> Path:
    """Return runtime yaml, copying the default template on first use only."""
    runtime = governance_yaml_runtime_path(agent_id)
    if runtime.is_file():
        return runtime

    template = default_governance_template_path()
    if not template.is_file():
        raise FileNotFoundError(
            f"Runtime governance config missing at {runtime} and no default template at {template}"
        )

    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, runtime)
    return runtime


def reset_runtime_governance_yaml(agent_id: str = HERMES_AGENT_ID) -> Path:
    """Overwrite runtime yaml from the default template (explicit reset)."""
    template = default_governance_template_path()
    if not template.is_file():
        raise FileNotFoundError(f"Default governance template missing: {template}")

    dest = governance_yaml_runtime_path(agent_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, dest)
    return dest


def write_scoped_governance_yaml(
    *,
    governed_tools: frozenset[str] | None = None,
    dest: Path | None = None,
) -> Path:
    """Write throwaway governance yaml with a chosen IntentFrame-governed tool subset.

    ``governed_tools=None`` marks every tool in the default template catalog as
    governed (yaml ``enabled: true``). This controls the plugin gate only — not
    which tools Hermes exposes on ``/v1/toolsets``.
    """
    template = default_governance_template_path()
    if not template.is_file():
        raise FileNotFoundError(f"Default governance template missing: {template}")

    raw: dict[str, Any] = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
    tools = raw.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise ValueError(f"Default governance template has no tools mapping: {template}")

    catalog = frozenset(str(name) for name in tools)
    if governed_tools is None:
        governed_set = catalog
    else:
        if not governed_tools:
            raise ValueError("At least one tool must be IntentFrame-governed")
        unknown = governed_tools - catalog
        if unknown:
            raise ValueError(
                f"Unknown governed tool(s) {sorted(unknown)!r}; "
                f"catalog: {sorted(catalog)!r}"
            )
        governed_set = governed_tools

    for name, spec in tools.items():
        if isinstance(spec, dict):
            spec["enabled"] = str(name) in governed_set

    if dest is None:
        prefix = (
            "hermes-governance-scoped-"
            if governed_tools is not None
            else "hermes-governance-catalog-"
        )
        dest = Path(tempfile.mkdtemp(prefix=prefix)) / "tools.yaml"

    dest = dest.expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        yaml.safe_dump(raw, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return dest


def write_catalog_all_governed_yaml(dest: Path | None = None) -> Path:
    """Write governance yaml with every catalog tool IntentFrame-governed."""
    return write_scoped_governance_yaml(governed_tools=None, dest=dest)


# Backward-compatible alias (prefer write_catalog_all_governed_yaml).
write_catalog_enabled_yaml = write_catalog_all_governed_yaml
