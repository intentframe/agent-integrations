"""Structured status report for ``intentframe-integrations status --json``.

Enforcement stack fields are shared with the control plane ``read_models`` views.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from intentframe_integrations.adapter_lifecycle import (
    adapter_pid_file,
    is_adapter_running,
)
from intentframe_integrations.hermes_gateway import gateway_pid_file, is_gateway_running
from intentframe_integrations.integration_pack import load_and_activate_pack
from intentframe_integrations.paths import list_agents


@dataclass
class AdapterStatus:
    agent_id: str
    running: bool
    pid: int | None
    socket: str


@dataclass
class StatusReport:
    bridge_socket: str
    bridge_present: bool
    gateway_running: bool
    gateway_pid: int | None
    adapters: list[AdapterStatus]
    backend_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def collect_status_report() -> StatusReport:
    bridge = Path.home() / ".intentframe" / "backend" / "bridge.sock"
    adapters: list[AdapterStatus] = []

    for agent in list_agents():
        try:
            pack = load_and_activate_pack(agent)
        except (FileNotFoundError, ValueError):
            continue
        if pack.adapter is None:
            continue
        agent_id = pack.agent.agent_id
        sock = pack.adapter.socket_path()
        running = is_adapter_running(agent_id) and sock.exists()
        adapters.append(
            AdapterStatus(
                agent_id=agent_id,
                running=running,
                pid=_read_pid(adapter_pid_file(agent_id)),
                socket=str(sock),
            )
        )

    gw_pid = _read_pid(gateway_pid_file())
    return StatusReport(
        bridge_socket=str(bridge),
        bridge_present=bridge.exists(),
        gateway_running=is_gateway_running(),
        gateway_pid=gw_pid if is_gateway_running() else None,
        adapters=adapters,
    )


def status_report_json() -> str:
    return json.dumps(collect_status_report().to_dict(), indent=2)
