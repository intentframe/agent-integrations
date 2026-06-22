"""Canonical governed-tool YAML paths and runtime materialization."""

from __future__ import annotations

import shutil
from pathlib import Path

from intentframe_integrations.paths import repo_root

HERMES_AGENT_ID = "hermes"
GOVERNANCE_RELATIVE = Path("integrations") / "hermes" / "governance" / "tools.yaml"


def canonical_governance_yaml_path() -> Path:
    """Single source of truth in the agent-integrations repo."""
    return repo_root() / GOVERNANCE_RELATIVE


def governance_yaml_runtime_path(agent_id: str = HERMES_AGENT_ID) -> Path:
    """Installed copy used by Hermes gateway/plugin at runtime."""
    return (
        Path.home()
        / ".intentframe"
        / "integrations"
        / agent_id
        / "governance"
        / "tools.yaml"
    )


def sync_governance_yaml(agent_id: str = HERMES_AGENT_ID) -> Path | None:
    """Copy canonical yaml to the runtime integrations tree. Returns dest or None if no repo."""
    src = canonical_governance_yaml_path()
    if not src.is_file():
        return None
    dest = governance_yaml_runtime_path(agent_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def ensure_governance_yaml_runtime(agent_id: str = HERMES_AGENT_ID) -> Path:
    """Sync from repo when available; otherwise require an existing runtime copy."""
    synced = sync_governance_yaml(agent_id)
    if synced is not None:
        return synced
    runtime = governance_yaml_runtime_path(agent_id)
    if runtime.is_file():
        return runtime
    raise FileNotFoundError(
        f"Governance contract missing at {runtime} and no canonical repo file at "
        f"{canonical_governance_yaml_path()}"
    )
