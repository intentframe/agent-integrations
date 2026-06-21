"""Resolve installed profile paths and runtime directories."""

from __future__ import annotations

import os
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

import intentframe_native_kit


def run_dir() -> Path:
    return Path(
        os.environ.get("INTENTFRAME_RUN_DIR", os.path.expanduser("~/.intentframe/run"))
    ).expanduser()


def state_dir() -> Path:
    return Path(
        os.environ.get(
            "IF_BACKEND_STATE_DIR",
            os.path.expanduser("~/.intentframe/backend"),
        )
    ).expanduser()


def supervisor_pid_file() -> Path:
    return state_dir() / "supervisor.pid"


def supervisor_log_file() -> Path:
    return state_dir() / "supervisor.log"


def executor_log_file() -> Path:
    return Path(
        os.environ.get(
            "INTENTFRAME_EXECUTOR_LOG",
            os.path.expanduser("~/.intentframe/logs/executor.log"),
        )
    ).expanduser()


def bridge_socket_path() -> Path:
    return Path(
        os.environ.get(
            "IF_SECURITY_BRIDGE_SOCKET",
            str(state_dir() / "bridge.sock"),
        )
    ).expanduser()


@lru_cache(maxsize=1)
def kit_dir() -> Path:
    return Path(intentframe_native_kit.__file__).resolve().parent


def supervisor_config_path() -> Path:
    override = os.environ.get("INTENTFRAME_SUPERVISOR_CONFIG")
    if override:
        return Path(override).expanduser()
    return kit_dir() / "supervisor_profile.yaml"


def bundled_config(*parts: str) -> Path:
    """Path to a file shipped under if_security_backend/config/."""
    return Path(str(files("if_security_backend").joinpath("config", *parts)))


def bundled_profile(name: str) -> Path:
    return bundled_config("profiles", name)


def core_config_path() -> Path:
    override = os.environ.get("INTENTFRAME_CORE_CONFIG")
    if override:
        return Path(override).expanduser()
    return bundled_profile("core.yaml")


def executor_config_path() -> Path:
    override = os.environ.get("EXECUTOR_CONFIG")
    if override:
        return Path(override).expanduser()
    return bundled_profile("executor.yaml")


def runtime_env() -> dict[str, str]:
    """Environment for supervisor child processes."""
    env = os.environ.copy()
    env.setdefault("INTENTFRAME_EXECUTOR_MODE", "real")
    env["INTENTFRAME_CORE_CONFIG"] = str(core_config_path())
    env["INTENTFRAME_SUPERVISOR_CONFIG"] = str(supervisor_config_path())
    env["EXECUTOR_CONFIG"] = str(executor_config_path())
    if key := os.environ.get("INTENTFRAME_EXECUTOR_HMAC_KEY"):
        env["INTENTFRAME_EXECUTOR_HMAC_KEY"] = key
    return env
