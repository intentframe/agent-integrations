"""Start/stop agent adapter sidecars."""

from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from intentframe_integrations.integration_pack import IntegrationPack


class AdapterError(Exception):
    pass


def integration_state_dir(agent_id: str) -> Path:
    return Path.home() / ".intentframe" / "integrations" / agent_id


def adapter_pid_file(agent_id: str) -> Path:
    return integration_state_dir(agent_id) / "adapter.pid"


def adapter_log_file(agent_id: str) -> Path:
    return integration_state_dir(agent_id) / "adapter.log"


def adapter_python() -> Path:
    """Interpreter used to launch adapter sidecars.

    The adapter runs in the same workspace environment as this CLI. Both dev and
    user installs provision that environment with ``uv sync --all-packages``,
    which installs the adapter package, so the sidecar is launched with the
    current interpreter. This keeps dev and user flows identical and removes any
    second venv built at runtime.
    """
    return Path(sys.executable)


def _read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _process_group_kwargs() -> dict[str, object]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        try:
            os.kill(pid, signal.CTRL_BREAK_EVENT)
            return
        except OSError:
            pass
    os.kill(pid, signal.SIGTERM)


def _kill_pid(pid: int) -> None:
    if os.name == "nt":
        os.kill(pid, signal.SIGTERM)
    else:
        os.kill(pid, signal.SIGKILL)


def is_adapter_running(agent_id: str) -> bool:
    pid = _read_pid(adapter_pid_file(agent_id))
    return pid is not None and _pid_alive(pid)


def adapter_top_package(pack: IntegrationPack) -> str:
    if pack.adapter is None:
        raise AdapterError(f"Agent {pack.agent.agent_id!r} has no adapter configured")
    return pack.adapter.module.split(".", 1)[0]


def adapter_importable(pack: IntegrationPack) -> bool:
    """True when the adapter package is importable in the current interpreter."""
    return importlib.util.find_spec(adapter_top_package(pack)) is not None


def ensure_adapter_importable(pack: IntegrationPack) -> None:
    """Fail early with actionable guidance if the adapter package is missing.

    The adapter runs in this CLI's interpreter; ``uv sync --all-packages``
    installs it for both dev and user installs. No second venv is built.
    """
    if not adapter_importable(pack):
        top_package = adapter_top_package(pack)
        raise AdapterError(
            f"Adapter package {top_package!r} is not importable in this "
            f"environment ({sys.executable}). Run: uv sync --all-packages"
        )


def _adapter_env(pack: IntegrationPack) -> dict[str, str]:
    env = os.environ.copy()
    agent = pack.agent
    env["INTENTFRAME_USER_ID"] = agent.user_id
    env["INTENTFRAME_AGENT_ID"] = agent.agent_id
    env["IF_AGENT_BRIDGE_SECRET"] = agent.bridge_secret

    bridge_socket = agent.env.get("IF_SECURITY_BRIDGE_SOCKET", "~/.intentframe/backend/bridge.sock")
    env.setdefault("IF_SECURITY_BRIDGE_SOCKET", os.path.expanduser(bridge_socket))
    for key, value in pack.agent.env.items():
        env.setdefault(key, os.path.expanduser(value))
    return env


def start_adapter(
    pack: IntegrationPack,
    *,
    detach: bool = True,
) -> int:
    if pack.adapter is None:
        raise AdapterError(f"Agent {pack.agent.agent_id!r} has no adapter configured")

    agent_id = pack.agent.agent_id
    if is_adapter_running(agent_id):
        pid = _read_pid(adapter_pid_file(agent_id))
        print(f"Adapter already running for {agent_id!r} (pid {pid})", file=sys.stderr)
        return pid or 0

    ensure_adapter_importable(pack)
    python_exe = adapter_python()
    sock = pack.adapter.socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.unlink(missing_ok=True)

    log_path = adapter_log_file(agent_id)
    log_fh = open(log_path, "a", encoding="utf-8")
    cmd = [
        str(python_exe),
        "-m",
        pack.adapter.module,
        "--socket",
        str(sock),
    ]

    print(f"Starting adapter for {agent_id!r} (log: {log_path})...", file=sys.stderr)
    proc = subprocess.Popen(
        cmd,
        env=_adapter_env(pack),
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        **_process_group_kwargs(),
    )
    adapter_pid_file(agent_id).write_text(str(proc.pid), encoding="utf-8")
    log_fh.close()

    if not detach:
        return proc.wait()

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if sock.exists():
            print(f"Adapter listening on {sock} (pid {proc.pid})")
            return proc.pid
        if not _pid_alive(proc.pid):
            tail = ""
            try:
                tail = log_path.read_text(encoding="utf-8")[-2000:]
            except OSError:
                pass
            raise AdapterError(f"Adapter exited during startup.\n{tail}")
        time.sleep(0.2)

    tail = ""
    try:
        tail = log_path.read_text(encoding="utf-8")[-2000:]
    except OSError:
        pass
    raise AdapterError(f"Adapter did not create socket within 10s: {sock}\n{tail}")


def stop_adapter(agent_id: str, *, timeout: float = 15.0, quiet: bool = False) -> None:
    adapter = integration_state_dir(agent_id)
    pid_file = adapter_pid_file(agent_id)
    pid = _read_pid(pid_file)

    if pid is None or not _pid_alive(pid):
        for spec in _adapter_socket_candidates(agent_id):
            spec.unlink(missing_ok=True)
        pid_file.unlink(missing_ok=True)
        if not quiet:
            print(f"Adapter for {agent_id!r} is not running.")
        return

    if not quiet:
        print(f"Stopping adapter for {agent_id!r} (pid {pid})...", file=sys.stderr)
    _terminate_pid(pid)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.25)
    if _pid_alive(pid):
        _kill_pid(pid)

    for spec in _adapter_socket_candidates(agent_id):
        spec.unlink(missing_ok=True)
    pid_file.unlink(missing_ok=True)
    if not quiet:
        print(f"Adapter for {agent_id!r} stopped.")


def _adapter_socket_candidates(agent_id: str) -> list[Path]:
    return [integration_state_dir(agent_id) / "adapter.sock"]


def adapter_status_line(pack: IntegrationPack) -> str:
    if pack.adapter is None:
        return "adapter: not configured"
    agent_id = pack.agent.agent_id
    sock = pack.adapter.socket_path()
    running = is_adapter_running(agent_id) and sock.exists()
    pid = _read_pid(adapter_pid_file(agent_id))
    return (
        f"adapter: {'running' if running else 'stopped'} "
        f"(pid={pid or 'none'}, socket={sock})"
    )
