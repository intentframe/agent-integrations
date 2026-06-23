"""Runtime policy.yaml materialization (mirrors governance/tools.yaml pattern)."""

from __future__ import annotations

import shutil
from pathlib import Path

from intentframe_integrations.integration_pack import IntegrationPack


def shipped_policy_template_path(pack: IntegrationPack) -> Path:
    """Default policy.yaml shipped with the agent integration pack."""
    if pack.agent.policy_file is None:
        raise FileNotFoundError(
            f"Agent {pack.agent.agent_id!r} has no policy_file in agent.json"
        )
    path = pack.agent.policy_file
    if not path.is_file():
        raise FileNotFoundError(f"Shipped policy template missing: {path}")
    return path


def policy_yaml_runtime_path(agent_id: str) -> Path:
    """User-owned runtime policy edited by the user or CLI."""
    return (
        Path.home()
        / ".intentframe"
        / "integrations"
        / agent_id
        / "policy.yaml"
    )


def ensure_runtime_policy_yaml(pack: IntegrationPack) -> Path:
    """Return runtime policy yaml, copying the shipped template on first use only."""
    runtime = policy_yaml_runtime_path(pack.agent.agent_id)
    if runtime.is_file():
        return runtime

    template = shipped_policy_template_path(pack)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, runtime)
    return runtime


def reset_runtime_policy_yaml(pack: IntegrationPack) -> Path:
    """Overwrite runtime policy from the shipped template (explicit reset)."""
    template = shipped_policy_template_path(pack)
    dest = policy_yaml_runtime_path(pack.agent.agent_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(template, dest)
    return dest


def install_policy_from_path(pack: IntegrationPack, src: Path) -> Path:
    """Copy an external policy file into the runtime location."""
    source = src.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Policy file not found: {source}")

    dest = policy_yaml_runtime_path(pack.agent.agent_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, dest)
    return dest
