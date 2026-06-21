"""Start/stop agent adapter sidecars."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from intentframe_integrations.integration_pack import IntegrationPack
from intentframe_integrations.paths import repo_root


class AdapterError(Exception):
    pass


def integration_state_dir(agent_id: str) -> Path:
    return Path.home() / ".intentframe" / "integrations" / agent_id


def adapter_pid_file(agent_id: str) -> Path:
    return integration_state_dir(agent_id) / "adapter.pid"


def adapter_log_file(agent_id: str) -> Path:
    return integration_state_dir(agent_id) / "adapter.log"


def adapter_venv_python(agent_id: str) -> Path:
    return integration_state_dir(agent_id) / ".venv" / "bin" / "python"


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


def is_adapter_running(agent_id: str) -> bool:
    pid = _read_pid(adapter_pid_file(agent_id))
    return pid is not None and _pid_alive(pid)


def _adapter_package_name(pack: IntegrationPack) -> str:
    pyproject = pack.adapter.source_dir / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data.get("project")
    if not isinstance(project, dict):
        raise AdapterError(f"Invalid adapter pyproject.toml: {pyproject}")
    name = project.get("name")
    if not isinstance(name, str) or not name.strip():
        raise AdapterError(f"adapter package name missing in {pyproject}")
    return name.strip()


def sync_adapter_venv(
    pack: IntegrationPack,
) -> Path:
    if pack.adapter is None:
        raise AdapterError(f"Agent {pack.agent.agent_id!r} has no adapter configured")

    if not pack.adapter.source_dir.is_dir():
        raise AdapterError(f"Adapter source not found: {pack.adapter.source_dir}")

    state_dir = integration_state_dir(pack.agent.agent_id)
    state_dir.mkdir(parents=True, exist_ok=True)
    venv_python = adapter_venv_python(pack.agent.agent_id)

    venv_dir = state_dir / ".venv"
    adapter_python = pack.adapter.python
    if not venv_python.is_file():
        subprocess.check_call(
            [
                "uv",
                "venv",
                str(venv_dir),
                "--python",
                adapter_python,
                "--no-project",
            ],
        )

    # Install from workspace lock via exported requirements (reproducible, Python 3.11+ venv).
    package_name = _adapter_package_name(pack)
    constraints = state_dir / "adapter-requirements.txt"
    subprocess.check_call(
        [
            "uv",
            "export",
            "--directory",
            str(repo_root()),
            "--package",
            package_name,
            "--no-hashes",
            "-q",
            "-o",
            str(constraints),
        ],
    )
    subprocess.check_call(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv_python),
            "--project",
            str(pack.adapter.source_dir),
            "-q",
            "-r",
            str(constraints),
        ],
    )
    return venv_python


def _adapter_env(pack: IntegrationPack) -> dict[str, str]:
    env = os.environ.copy()
    agent = pack.agent
    env["INTENTFRAME_USER_ID"] = agent.user_id
    env["INTENTFRAME_AGENT_ID"] = agent.agent_id
    env["IF_AGENT_BRIDGE_SECRET"] = agent.bridge_secret

    bridge_socket = agent.env.get("IF_SECURITY_BRIDGE_SOCKET", "~/.intentframe/backend/bridge.sock")
    env["IF_SECURITY_BRIDGE_SOCKET"] = os.path.expanduser(bridge_socket)
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

    venv_python = sync_adapter_venv(pack)
    sock = pack.adapter.socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.unlink(missing_ok=True)

    log_path = adapter_log_file(agent_id)
    log_fh = open(log_path, "a", encoding="utf-8")
    cmd = [
        str(venv_python),
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
        start_new_session=True,
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
    os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.25)
    if _pid_alive(pid):
        os.kill(pid, signal.SIGKILL)

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
