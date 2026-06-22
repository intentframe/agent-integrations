"""Default governance template path and runtime user config materialization."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from intentframe_integrations.paths import repo_root

HERMES_AGENT_ID = "hermes"
DEFAULT_GOVERNANCE_TEMPLATE_RELATIVE = Path("integrations") / "hermes" / "governance" / "tools.yaml"


def default_governance_template_path() -> Path:
    """Default tools.yaml shipped with the repo (reference template only)."""
    return repo_root() / DEFAULT_GOVERNANCE_TEMPLATE_RELATIVE


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


def write_catalog_enabled_yaml(dest: Path | None = None) -> Path:
    """Write governance yaml with every catalog tool enabled."""
    template = default_governance_template_path()
    if not template.is_file():
        raise FileNotFoundError(f"Default governance template missing: {template}")

    raw: dict[str, Any] = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
    tools = raw.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise ValueError(f"Default governance template has no tools mapping: {template}")

    for spec in tools.values():
        if isinstance(spec, dict):
            spec["enabled"] = True

    if dest is None:
        dest = Path(tempfile.mkdtemp(prefix="hermes-governance-catalog-")) / "tools.yaml"

    dest = dest.expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        yaml.safe_dump(raw, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )
    return dest
