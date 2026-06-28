"""Start/stop/status for the IntentFrame control plane HTTP server."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from intentframe_control_plane.config import (
    LOG_FILE,
    PID_FILE,
    ControlPlaneSettings,
    validate_bind_host,
)


class ControlPlaneError(Exception):
    pass


@dataclass(frozen=True)
class ControlPlaneStatus:
    running: bool
    pid: int | None
    host: str
    port: int
    url: str
    healthy: bool


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


def is_control_plane_running() -> bool:
    pid = _read_pid(PID_FILE)
    if pid is None:
        return False
    if not _pid_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        return False
    return True


def _health_host(bind_host: str) -> str:
    """Map bind-all addresses to a loopback host for HTTP health probes."""
    if bind_host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return bind_host


def _health_check(host: str, port: int, *, timeout: float = 2.0) -> bool:
    url = f"http://{host}:{port}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return resp.status == 200
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def control_plane_status(settings: ControlPlaneSettings | None = None) -> ControlPlaneStatus:
    cfg = settings or ControlPlaneSettings.from_env()
    pid = _read_pid(PID_FILE)
    running = pid is not None and _pid_alive(pid)
    if not running:
        pid = None
    healthy = running and _health_check(_health_host(cfg.host), cfg.port)
    return ControlPlaneStatus(
        running=running,
        pid=pid,
        host=cfg.host,
        port=cfg.port,
        url=cfg.url,
        healthy=healthy,
    )


def format_status_line(status: ControlPlaneStatus) -> str:
    state = "running" if status.running else "stopped"
    health = "healthy" if status.healthy else "unhealthy" if status.running else "n/a"
    return (
        f"control-plane: {state} (pid={status.pid or 'none'}, "
        f"url={status.url}, health={health})"
    )


def start_control_plane(
    *,
    host: str | None = None,
    port: int | None = None,
    quiet: bool = False,
) -> ControlPlaneStatus:
    settings = ControlPlaneSettings.from_env()
    bind_host = host or settings.host
    bind_port = port if port is not None else settings.port
    validate_bind_host(bind_host, allow_remote=settings.allow_remote)

    existing = control_plane_status(
        ControlPlaneSettings(host=bind_host, port=bind_port, token=settings.token, allow_remote=settings.allow_remote)
    )
    if existing.running and existing.healthy:
        if not quiet:
            print(f"Control plane already running at {existing.url}", file=sys.stderr)
        return existing

    if existing.running:
        stop_control_plane(quiet=True)

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["INTENTFRAME_CONTROL_PLANE_HOST"] = bind_host
    env["INTENTFRAME_CONTROL_PLANE_PORT"] = str(bind_port)
    if settings.token:
        env.setdefault("INTENTFRAME_CONTROL_PLANE_TOKEN", settings.token)

    try:
        from intentframe_control_plane.cli_runner import resolve_cli_bin

        env["INTENTFRAME_INTEGRATIONS_BIN"] = resolve_cli_bin()
    except RuntimeError:
        pass

    log_fh = open(LOG_FILE, "a", encoding="utf-8")
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "intentframe_control_plane.server:app",
        "--host",
        bind_host,
        "--port",
        str(bind_port),
        "--log-level",
        "info",
    ]
    if not quiet:
        print(f"Starting control plane at http://{bind_host}:{bind_port}...", file=sys.stderr)

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        **_process_group_kwargs(),
    )
    proc_pid = proc.pid
    PID_FILE.write_text(str(proc_pid), encoding="utf-8")
    log_fh.close()

    health_host = _health_host(bind_host)

    deadline = time.monotonic() + 30.0
    while time.monotonic() < deadline:
        if _health_check(health_host, bind_port, timeout=1.0):
            status = control_plane_status(
                ControlPlaneSettings(
                    host=bind_host,
                    port=bind_port,
                    token=settings.token,
                    allow_remote=settings.allow_remote,
                )
            )
            if not quiet:
                print(f"Control plane ready at {status.url}")
            return status
        if not _pid_alive(proc_pid):
            tail = ""
            try:
                tail = LOG_FILE.read_text(encoding="utf-8")[-2000:]
            except OSError:
                pass
            PID_FILE.unlink(missing_ok=True)
            raise ControlPlaneError(f"Control plane exited during startup.\n{tail}")
        time.sleep(0.1)

    if _pid_alive(proc_pid):
        _terminate_pid(proc_pid)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _pid_alive(proc_pid):
            time.sleep(0.1)
        if _pid_alive(proc_pid):
            _kill_pid(proc_pid)
    PID_FILE.unlink(missing_ok=True)
    tail = ""
    try:
        tail = LOG_FILE.read_text(encoding="utf-8")[-2000:]
    except OSError:
        pass
    raise ControlPlaneError(
        f"Control plane did not become healthy within 30s (log: {LOG_FILE})\n{tail}"
    )


def stop_control_plane(*, timeout: float = 15.0, quiet: bool = False) -> None:
    pid = _read_pid(PID_FILE)
    if pid is None or not _pid_alive(pid):
        PID_FILE.unlink(missing_ok=True)
        if not quiet:
            print("Control plane is not running.", file=sys.stderr)
        return

    if not quiet:
        print(f"Stopping control plane (pid {pid})...", file=sys.stderr)
    _terminate_pid(pid)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.1)
    if _pid_alive(pid):
        _kill_pid(pid)

    PID_FILE.unlink(missing_ok=True)
    if not quiet:
        print("Control plane stopped.")


def serve_control_plane(
    *,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Run control plane in foreground (no PID file)."""
    import uvicorn

    settings = ControlPlaneSettings.from_env()
    bind_host = host or settings.host
    bind_port = port if port is not None else settings.port
    validate_bind_host(bind_host, allow_remote=settings.allow_remote)

    os.environ["INTENTFRAME_CONTROL_PLANE_HOST"] = bind_host
    os.environ["INTENTFRAME_CONTROL_PLANE_PORT"] = str(bind_port)

    uvicorn.run(
        "intentframe_control_plane.server:app",
        host=bind_host,
        port=bind_port,
        log_level="info",
    )
