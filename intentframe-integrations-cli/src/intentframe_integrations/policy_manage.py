"""Load runtime policy YAML into policy-registry (validate + upsert)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from intentframe_integrations.integration_pack import IntegrationPack, load_integration_pack
from intentframe_integrations.paths import agent_config_path
from intentframe_integrations.policy_contract import (
    ensure_runtime_policy_yaml,
    install_policy_from_path,
    policy_yaml_runtime_path,
    reset_runtime_policy_yaml,
    shipped_policy_template_path,
)


class PolicyError(Exception):
    pass


@dataclass(frozen=True)
class PolicyShowReport:
    agent_id: str
    user_id: str
    runtime_path: Path
    runtime_exists: bool
    shipped_template: Path
    registry_loaded: bool
    registry_action_count: int | None
    registry_message: str


def _load_pack(agent: str) -> IntegrationPack:
    return load_integration_pack(agent_config_path(agent))


def _resolve_policy_path(yaml_path: Path) -> Path:
    path = yaml_path.expanduser().resolve()
    if not path.is_file():
        raise PolicyError(f"Policy file not found: {path}")
    return path


def _validate_policy_agent_id(yaml_path: Path, expected_agent_id: str) -> None:
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise PolicyError(f"Could not read policy file: {exc}") from exc
    if not isinstance(raw, dict):
        raise PolicyError(f"Policy yaml must be a mapping: {yaml_path}")

    agent_id = raw.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id.strip():
        raise PolicyError(f"Policy yaml missing agent_id: {yaml_path}")
    if agent_id.strip() != expected_agent_id:
        raise PolicyError(
            f"Policy agent_id {agent_id!r} does not match integration "
            f"profile {expected_agent_id!r}"
        )


def validate_policy_file(pack: IntegrationPack, yaml_path: Path) -> None:
    """Validate policy yaml structure and bundle semantics without registry writes."""
    path = _resolve_policy_path(yaml_path)
    _validate_policy_agent_id(path, pack.agent.agent_id)

    from intentframe_bundle_sdk.loader import validate_policy_with_bundles
    from if_security_backend.runtime.policy import DEFAULT_BUNDLE
    from policy_registry.seeds import load_policy_seed

    try:
        policy = load_policy_seed(
            path,
            user_id=pack.agent.user_id,
            agent_id=pack.agent.agent_id,
        )
        validate_policy_with_bundles(policy, [DEFAULT_BUNDLE])
    except Exception as exc:
        raise PolicyError(str(exc)) from exc


def seed_agent_policy_from_file(
    pack: IntegrationPack,
    yaml_path: Path,
    *,
    skip_if_exists: bool = False,
) -> None:
    """Validate policy yaml and upsert into policy-registry."""
    path = _resolve_policy_path(yaml_path)
    validate_policy_file(pack, path)

    from if_security_backend.runtime.policy import seed_policy

    try:
        seed_policy(
            yaml_path=path,
            user_id=pack.agent.user_id,
            agent_id=pack.agent.agent_id,
            skip_if_exists=skip_if_exists,
        )
    except Exception as exc:
        raise PolicyError(str(exc)) from exc


def _policy_file_error(exc: BaseException) -> PolicyError:
    if isinstance(exc, PolicyError):
        return exc
    return PolicyError(str(exc))


def _registry_status(pack: IntegrationPack) -> tuple[bool, int | None, str]:
    from if_security_backend.runtime.paths import run_dir
    from policy_registry.client import PolicyRegistryClient

    socket = run_dir() / "policy-registry.sock"
    if not socket.exists():
        return False, None, "policy-registry not running (start the runtime first)"

    try:
        with PolicyRegistryClient(socket_path=str(socket)) as client:
            policy = client.get_user_policy(pack.agent.user_id, pack.agent.agent_id)
    except KeyError:
        return False, None, "not seeded in registry"
    except OSError as exc:
        return False, None, f"registry unreachable: {exc}"

    count = len(policy.allowed_actions)
    return True, count, f"loaded ({count} allowed action(s))"


def policy_show(agent: str) -> PolicyShowReport:
    pack = _load_pack(agent)
    runtime = policy_yaml_runtime_path(pack.agent.agent_id)
    try:
        shipped = shipped_policy_template_path(pack)
    except FileNotFoundError as exc:
        raise PolicyError(str(exc)) from exc
    loaded, action_count, message = _registry_status(pack)
    return PolicyShowReport(
        agent_id=pack.agent.agent_id,
        user_id=pack.agent.user_id,
        runtime_path=runtime,
        runtime_exists=runtime.is_file(),
        shipped_template=shipped,
        registry_loaded=loaded,
        registry_action_count=action_count,
        registry_message=message,
    )


def format_policy_show(report: PolicyShowReport) -> str:
    lines = [
        f"Policy ({report.agent_id}):",
        f"  user_id:          {report.user_id}",
        f"  runtime file:     {report.runtime_path}",
        f"  runtime present:  {'yes' if report.runtime_exists else 'no'}",
        f"  shipped template: {report.shipped_template}",
        f"  registry:         {report.registry_message}",
    ]
    return "\n".join(lines)


def policy_reload(agent: str) -> Path:
    """Re-read runtime policy file and upsert into policy-registry."""
    pack = _load_pack(agent)
    try:
        path = ensure_runtime_policy_yaml(pack)
    except FileNotFoundError as exc:
        raise _policy_file_error(exc) from exc
    seed_agent_policy_from_file(pack, path)
    return path


def policy_set(agent: str, src: Path) -> Path:
    """Validate external policy, copy to runtime, and load into registry."""
    pack = _load_pack(agent)
    source = src.expanduser().resolve()
    validate_policy_file(pack, source)
    path = install_policy_from_path(pack, source)
    seed_agent_policy_from_file(pack, path)
    return path


def policy_reset(agent: str) -> Path:
    """Restore shipped default to runtime location and load into registry."""
    pack = _load_pack(agent)
    try:
        path = reset_runtime_policy_yaml(pack)
    except FileNotFoundError as exc:
        raise _policy_file_error(exc) from exc
    seed_agent_policy_from_file(pack, path)
    return path
