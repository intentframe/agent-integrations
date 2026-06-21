"""Resolve repo root and integration agent profile paths."""

from __future__ import annotations

import subprocess
from pathlib import Path

# agent name → agent.json path relative to repo root
AGENT_PROFILES: dict[str, str] = {
    "hermes": "integrations/hermes/agent.json",
}


def repo_root() -> Path:
    env = __import__("os").environ.get("INTENTFRAME_INTEGRATIONS_ROOT")
    if env:
        return Path(env).expanduser().resolve()

    here = Path(__file__).resolve()
    # …/intentframe-integrations-cli/src/intentframe_integrations/paths.py
    candidate = here.parents[3]
    if (candidate / "integrations").is_dir() and (candidate / "if-integration-backend").is_dir():
        return candidate

    try:
        out = subprocess.check_output(
            ["git", "-C", str(candidate), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return Path(out.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    return candidate


def agent_config_path(agent: str) -> Path:
    rel = AGENT_PROFILES.get(agent)
    if not rel:
        known = ", ".join(sorted(AGENT_PROFILES))
        raise ValueError(f"Unknown agent {agent!r} (known: {known})")
    path = repo_root() / rel
    if not path.is_file():
        raise FileNotFoundError(f"Agent config not found: {path}")
    return path


def list_agents() -> tuple[str, ...]:
    return tuple(sorted(AGENT_PROFILES))


def bridge_client_dir() -> Path:
    return repo_root() / "if-integration-clients" / "python"
