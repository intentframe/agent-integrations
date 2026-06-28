"""Read-only views of runtime state without subprocess side effects.

Used by ``GET /api/status``, ``/api/governance``, and ``/api/policy`` so page loads
do not spawn CLI subprocesses or mutate runtime state.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from intentframe_control_plane.config import (
    BRIDGE_SOCKET,
    INTENTFRAME_HOME,
    POLICY_RUNTIME,
)

HERMES_AGENT_ID = "hermes"
INTEGRATION_DIR = INTENTFRAME_HOME / "integrations" / HERMES_AGENT_ID
GOVERNANCE_YAML = INTEGRATION_DIR / "governance" / "tools.yaml"
GATEWAY_PID_FILE = INTEGRATION_DIR / "gateway.pid"
ADAPTER_PID_FILE = INTEGRATION_DIR / "adapter.pid"
ADAPTER_SOCKET = INTEGRATION_DIR / "adapter.sock"
POLICY_REGISTRY_SOCKET = INTENTFRAME_HOME / "run" / "policy-registry.sock"


def _read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _gateway_running() -> bool:
    pid = _read_pid(GATEWAY_PID_FILE)
    return pid is not None and _pid_alive(pid)


def _adapter_running() -> bool:
    pid = _read_pid(ADAPTER_PID_FILE)
    return pid is not None and _pid_alive(pid) and ADAPTER_SOCKET.exists()


def collect_status_dict() -> dict[str, Any]:
    gw_running = _gateway_running()
    gw_pid = _read_pid(GATEWAY_PID_FILE) if gw_running else None
    adapter_running = _adapter_running()
    return {
        "bridge_socket": str(BRIDGE_SOCKET),
        "bridge_present": BRIDGE_SOCKET.exists(),
        "gateway_running": gw_running,
        "gateway_pid": gw_pid,
        "adapters": [
            {
                "agent_id": HERMES_AGENT_ID,
                "running": adapter_running,
                "pid": _read_pid(ADAPTER_PID_FILE) if adapter_running else None,
                "socket": str(ADAPTER_SOCKET),
            }
        ],
    }


def load_governance_dict() -> dict[str, Any]:
    if not GOVERNANCE_YAML.is_file():
        return {"agent": HERMES_AGENT_ID, "tools": [], "runtime_governed": []}

    raw = yaml.safe_load(GOVERNANCE_YAML.read_text(encoding="utf-8")) or {}
    tools_map = raw.get("tools") if isinstance(raw, dict) else None
    if not isinstance(tools_map, dict):
        return {"agent": HERMES_AGENT_ID, "tools": [], "runtime_governed": []}

    tools: list[dict[str, Any]] = []
    runtime_governed: list[str] = []
    for name, spec in tools_map.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            continue
        enabled = spec.get("enabled", True)
        if not isinstance(enabled, bool):
            enabled = True
        tools.append({"name": name, "enabled": enabled})
        if enabled:
            runtime_governed.append(name)

    tools.sort(key=lambda item: item["name"])
    runtime_governed.sort()
    return {
        "agent": HERMES_AGENT_ID,
        "tools": tools,
        "runtime_governed": runtime_governed,
    }


def _registry_message() -> tuple[bool, int | None, str]:
    if not POLICY_REGISTRY_SOCKET.exists():
        return False, None, "policy-registry not running (start the enforcement stack first)"
    return False, None, "registry socket present (reload policy after stack start to verify load)"


def load_policy_dict() -> dict[str, Any]:
    runtime_exists = POLICY_RUNTIME.is_file()
    yaml_text = ""
    if runtime_exists:
        yaml_text = POLICY_RUNTIME.read_text(encoding="utf-8")

    agent_id = HERMES_AGENT_ID
    user_id = "default"
    if runtime_exists:
        try:
            raw = yaml.safe_load(yaml_text) or {}
            if isinstance(raw, dict):
                if isinstance(raw.get("agent_id"), str):
                    agent_id = raw["agent_id"]
                if isinstance(raw.get("user_id"), str):
                    user_id = raw["user_id"]
        except yaml.YAMLError:
            pass

    loaded, action_count, message = _registry_message()
    return {
        "meta": {
            "agent_id": agent_id,
            "user_id": user_id,
            "runtime_path": str(POLICY_RUNTIME),
            "runtime_exists": runtime_exists,
            "shipped_template": "",
            "registry_loaded": loaded,
            "registry_action_count": action_count,
            "registry_message": message,
        },
        "yaml": yaml_text,
    }


def tail_log_lines(path: Path, *, max_lines: int) -> list[str]:
    """Return the last max_lines from a text file without loading the whole file."""
    if not path.is_file():
        return []

    chunk_size = 8192
    data = b""
    with path.open("rb") as fh:
        fh.seek(0, os.SEEK_END)
        position = fh.tell()
        while position > 0 and data.count(b"\n") <= max_lines:
            read_size = min(chunk_size, position)
            position -= read_size
            fh.seek(position)
            data = fh.read(read_size) + data

    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()
    return lines[-max_lines:]


def public_config_dict() -> dict[str, str]:
    host = os.environ.get("HERMES_DASHBOARD_HOST", "127.0.0.1")
    port = os.environ.get("HERMES_DASHBOARD_PORT", "9119")
    return {"hermes_chat_url": f"http://{host}:{port}/chat"}
