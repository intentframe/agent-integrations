"""Start/stop the bridge UDS server."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from if_security_backend.bridge.config import BridgeConfigError, bridge_config_path, load_bridge_agents
from if_security_backend.runtime.health import core_healthy
from if_security_backend.runtime.paths import bridge_socket_path, state_dir


class BridgeError(Exception):
    pass


def bridge_pid_file() -> Path:
    return state_dir() / "bridge.pid"


def bridge_log_file() -> Path:
    return state_dir() / "bridge.log"


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


def is_bridge_running() -> bool:
    pid = _read_pid(bridge_pid_file())
    return pid is not None and _pid_alive(pid)


def start_bridge(*, detach: bool = False, config_path: Path | None = None) -> int:
    cfg_path = config_path or bridge_config_path()
    try:
        load_bridge_agents(cfg_path)
    except BridgeConfigError as exc:
        raise BridgeError(str(exc)) from exc

    if is_bridge_running():
        pid = _read_pid(bridge_pid_file())
        print(f"Bridge already running (pid {pid})", file=sys.stderr)
        return pid or 0

    if not core_healthy():
        raise BridgeError("IntentFrame core is not healthy — run: if-integration-backend start")

    sock = bridge_socket_path()
    sock.parent.mkdir(parents=True, exist_ok=True)
    sock.unlink(missing_ok=True)

    if detach:
        print(f"Starting bridge (log: {bridge_log_file()})...", file=sys.stderr)
        log_path = bridge_log_file()
        log_fh = open(log_path, "a", encoding="utf-8")
        cmd = [
            sys.executable,
            "-m",
            "if_security_backend.bridge.main",
            "--socket",
            str(sock),
            "--config",
            str(cfg_path),
        ]
        proc = subprocess.Popen(
            cmd,
            env=os.environ.copy(),
            stdout=log_fh,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        bridge_pid_file().write_text(str(proc.pid), encoding="utf-8")
        log_fh.close()

        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            if sock.exists():
                print(f"Bridge listening on {sock} (pid {proc.pid})")
                return proc.pid
            if not _pid_alive(proc.pid):
                tail = ""
                try:
                    tail = log_path.read_text(encoding="utf-8")[-2000:]
                except OSError:
                    pass
                raise BridgeError(f"Bridge exited during startup.\n{tail}")
            time.sleep(0.2)
        tail = ""
        try:
            tail = log_path.read_text(encoding="utf-8")[-2000:]
        except OSError:
            pass
        raise BridgeError(f"Bridge did not create socket within 10s: {sock}\n{tail}")

    from if_security_backend.bridge.main import run_server

    run_server(socket_path=sock, config_path=cfg_path)
    return os.getpid()


def stop_bridge(*, timeout: float = 15.0, quiet: bool = False) -> None:
    sock = bridge_socket_path()
    pid = _read_pid(bridge_pid_file())

    if pid is None or not _pid_alive(pid):
        sock.unlink(missing_ok=True)
        try:
            bridge_pid_file().unlink(missing_ok=True)
        except OSError:
            pass
        if not quiet:
            print("Bridge is not running.")
        return

    if not quiet:
        print(f"Stopping bridge (pid {pid})...", file=sys.stderr)
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.25)
    if _pid_alive(pid):
        os.kill(pid, signal.SIGKILL)

    sock.unlink(missing_ok=True)
    try:
        bridge_pid_file().unlink(missing_ok=True)
    except OSError:
        pass
    if not quiet:
        print("Bridge stopped.")
