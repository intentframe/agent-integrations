"""Seed agent policy into policy-registry over UDS."""

from __future__ import annotations

import os
from pathlib import Path

from intentframe_bundle_sdk.loader import validate_policy_with_bundles
from policy_registry.client import PolicyRegistryClient
from policy_registry.seeds import load_policy_seed

from if_security_backend.agent_config import default_test_policy_path, load_agent_pack
from if_security_backend.runtime.bundles import load_core_bundle_packages
from if_security_backend.runtime.paths import run_dir


def resolve_user_id(explicit: str | None = None) -> str:
    user_id = explicit or os.environ.get("INTENTFRAME_USER_ID")
    if not user_id:
        raise ValueError(
            "Set INTENTFRAME_USER_ID or pass --user-id (policy registry operator id)."
        )
    return user_id


def resolve_policy_path(
    explicit: Path | None,
    *,
    agent_config: Path | None = None,
) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    if agent_config is not None:
        pack = load_agent_pack(agent_config.expanduser())
        if pack.policy_file is not None:
            return pack.policy_file
    return default_test_policy_path()


def resolve_agent_id(explicit: str | None, *, agent_config: Path | None = None) -> str:
    if explicit:
        return explicit
    if agent_config is not None:
        return load_agent_pack(agent_config.expanduser()).agent_id
    import yaml

    data = yaml.safe_load(default_test_policy_path().read_text(encoding="utf-8")) or {}
    agent_id = data.get("agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("Could not resolve agent_id — pass --agent-id or --agent-config")
    return agent_id


def seed_policy(
    *,
    yaml_path: Path,
    user_id: str,
    agent_id: str,
    skip_if_exists: bool = False,
    validate_bundles: bool = True,
) -> None:
    policy = load_policy_seed(
        yaml_path,
        user_id=user_id,
        agent_id=agent_id,
    )

    if validate_bundles:
        validate_policy_with_bundles(policy, load_core_bundle_packages())

    socket = str(run_dir() / "policy-registry.sock")
    with PolicyRegistryClient(socket_path=socket) as client:
        if skip_if_exists:
            try:
                client.get_user_policy(user_id, agent_id)
                print(f"Policy already exists for ({user_id}, {agent_id}) — skipping")
                return
            except KeyError:
                pass
        client.set_user_policy(policy)
        print(f"Policy seeded for user={user_id!r} agent={agent_id!r}")
