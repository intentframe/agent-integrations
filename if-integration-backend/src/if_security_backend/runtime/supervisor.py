"""Supervisor process lifecycle (background start/stop)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from if_security_backend.bridge.config import persist_bridge_config_path
from if_security_backend.bridge.runner import BridgeError, is_bridge_running, start_bridge, stop_bridge
from if_security_backend.runtime.health import core_healthy
from if_security_backend.runtime.paths import (
    core_config_path,
    executor_config_path,
    executor_log_file,
    run_dir,
    runtime_env,
    state_dir,
    supervisor_config_path,
    supervisor_log_file,
    supervisor_pid_file,
)

_FAIL_MARKERS = (
    "Startup failed",
    "Application startup failed",
    "ConfigurationError:",
    "Services failed to start",
    "executor failed health check",
)


class SupervisorError(Exception):
    """Failed to start or stop the IntentFrame runtime."""


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


def _validate_configs() -> None:
    for label, path in (
        ("core", core_config_path()),
        ("executor", executor_config_path()),
        ("supervisor", supervisor_config_path()),
    ):
        if not path.is_file():
            raise SupervisorError(f"Missing {label} config: {path}")


def is_supervisor_running() -> bool:
    pid = _read_pid(supervisor_pid_file())
    return pid is not None and _pid_alive(pid)


def _log_tail(path: Path, max_chars: int = 4000) -> str:
    try:
        return path.read_text(encoding="utf-8")[-max_chars:]
    except OSError:
        return "(unreadable)"


def _drain_new_lines(
    path: Path,
    offset: int,
    *,
    prefix: str,
    out: object = sys.stderr,
) -> tuple[int, str | None]:
    """Print new log bytes since offset. Returns (new_offset, fail_reason)."""
    if not path.is_file():
        return offset, None
    try:
        data = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return offset, None
    if len(data) <= offset:
        return offset, None
    chunk = data[offset:]
    for line in chunk.splitlines():
        print(f"[{prefix}] {line}", file=out)
        if any(marker in line for marker in _FAIL_MARKERS):
            return len(data), line.strip()
    return len(data), None


def _wait_for_core_with_logs(
    *,
    supervisor_pid: int,
    log_paths: list[tuple[Path, str]],
    timeout: float,
    poll_interval: float = 0.5,
) -> tuple[bool, str | None]:
    """Poll health, stream logs to stderr, fail fast on startup errors."""
    offsets = {path: path.stat().st_size if path.is_file() else 0 for path, _ in log_paths}
    deadline = time.monotonic() + timeout
    started = time.monotonic()
    last_progress = -1

    while time.monotonic() < deadline:
        if not _pid_alive(supervisor_pid):
            for path, prefix in log_paths:
                offsets[path], _ = _drain_new_lines(path, offsets[path], prefix=prefix)
            return False, "Supervisor process exited — startup failed"

        fail_reason: str | None = None
        for path, prefix in log_paths:
            offsets[path], reason = _drain_new_lines(path, offsets[path], prefix=prefix)
            if reason and fail_reason is None:
                fail_reason = reason

        if fail_reason:
            time.sleep(0.5)
            for path, prefix in log_paths:
                offsets[path], _ = _drain_new_lines(path, offsets[path], prefix=prefix)
            return False, fail_reason

        if core_healthy():
            for path, prefix in log_paths:
                offsets[path], _ = _drain_new_lines(path, offsets[path], prefix=prefix)
            return True, None

        elapsed = int(time.monotonic() - started)
        if elapsed // 5 > last_progress // 5:
            print(f"... waiting for core ({elapsed}s)", file=sys.stderr)
            last_progress = elapsed

        time.sleep(poll_interval)

    for path, prefix in log_paths:
        offsets[path], _ = _drain_new_lines(path, offsets[path], prefix=prefix)
    return False, f"Core did not become healthy within {timeout:.0f}s"


def start_supervisor(
    *,
    wait: bool = True,
    timeout: float = 90.0,
    bridge_config: Path | None = None,
    start_bridge_server: bool = True,
) -> int:
    """Start supervisor + bridge in the background. Returns wrapper PID."""
    _validate_configs()
    state_dir().mkdir(parents=True, exist_ok=True)

    if is_supervisor_running():
        pid = _read_pid(supervisor_pid_file())
        raise SupervisorError(f"Supervisor already running (pid {pid})")

    if is_bridge_running() and not core_healthy():
        stop_bridge(quiet=True)

    if core_healthy():
        raise SupervisorError(
            "IntentFrame core is already healthy on UDS — another runtime may be "
            "running. Stop it before starting if-integration-backend runtime."
        )

    log_path = supervisor_log_file()
    executor_log = executor_log_file()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    executor_log.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "a", encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "supervisor.main",
        "start",
        "--config",
        str(supervisor_config_path()),
    ]
    env = runtime_env()

    if not env.get("OPENAI_API_KEY"):
        print(
            "WARNING: OPENAI_API_KEY is unset — Guardian / Analysis Engine may fail",
            file=sys.stderr,
        )

    print(f"Starting supervisor (log: {log_path})", file=sys.stderr)
    print(f"Executor log: {executor_log}", file=sys.stderr)

    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    supervisor_pid_file().write_text(str(proc.pid), encoding="utf-8")
    log_fh.close()

    if wait or start_bridge_server:
        print("Waiting for core health...", file=sys.stderr)
        ok, reason = _wait_for_core_with_logs(
            supervisor_pid=proc.pid,
            log_paths=[(log_path, "supervisor"), (executor_log, "executor")],
            timeout=timeout,
        )
        if not ok:
            raise SupervisorError(
                f"{reason}\n"
                f"Supervisor log: {log_path}\n"
                f"Executor log: {executor_log}\n"
                f"--- supervisor tail ---\n{_log_tail(log_path)}\n"
                f"--- executor tail ---\n{_log_tail(executor_log)}"
            )
        print("Core healthy.", file=sys.stderr)

    if start_bridge_server:
        from if_security_backend.agent_config import default_test_agent_pack_path

        cfg = bridge_config or default_test_agent_pack_path()
        persist_bridge_config_path(cfg)
        try:
            start_bridge(detach=True, config_path=cfg)
        except BridgeError as exc:
            stop_supervisor()
            raise SupervisorError(str(exc)) from exc

    return proc.pid


_SOCKET_NAMES = (
    "policy-registry.sock",
    "resource-registry.sock",
    "executor.sock",
    "intentframe.sock",
)


def _stop_pid(pid: int, *, timeout: float, use_group: bool) -> None:
    """SIGTERM then SIGKILL a process (optionally its process group)."""
    def _signal(sig: int) -> None:
        if use_group:
            try:
                os.killpg(pid, sig)
                return
            except ProcessLookupError:
                pass
            except PermissionError:
                pass
        os.kill(pid, sig)

    try:
        _signal(signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        return

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.5)

    if _pid_alive(pid):
        try:
            _signal(signal.SIGKILL)
        except OSError:
            pass


def _stop_socket_holders(run_dir_path: Path, *, timeout: float) -> None:
    """Kill processes still bound to IntentFrame UDS sockets (best-effort)."""
    import shutil
    import subprocess

    if not shutil.which("lsof"):
        return

    for sock_name in _SOCKET_NAMES:
        sock = run_dir_path / sock_name
        if not sock.exists():
            continue
        result = subprocess.run(
            ["lsof", "-t", str(sock)],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line.isdigit():
                continue
            holder = int(line)
            if _pid_alive(holder):
                print(f"Stopping pid {holder} (holding {sock_name})...", file=sys.stderr)
                _stop_pid(holder, timeout=timeout, use_group=False)


def stop_supervisor(*, timeout: float = 30.0) -> None:
    """Stop bridge, supervisor, and IntentFrame services."""
    stop_bridge(quiet=True)

    run_dir_path = run_dir()
    substrate_pid_file = run_dir_path / "supervisor.pid"
    wrapper_pid_file = supervisor_pid_file()

    substrate_pid = _read_pid(substrate_pid_file)
    wrapper_pid = _read_pid(wrapper_pid_file)
    any_alive = (
        (substrate_pid is not None and _pid_alive(substrate_pid))
        or (wrapper_pid is not None and _pid_alive(wrapper_pid))
        or core_healthy()
    )
    any_artifacts = (
        any_alive
        or substrate_pid_file.is_file()
        or wrapper_pid_file.is_file()
        or any((run_dir_path / n).exists() for n in _SOCKET_NAMES)
    )

    if not any_artifacts:
        print("Runtime is not running.")
        return

    stopped_any = False
    seen: set[int] = set()

    for label, pid, use_group in (
        ("supervisor", substrate_pid, True),
        ("wrapper", wrapper_pid, True),
    ):
        if pid is None or pid in seen or not _pid_alive(pid):
            continue
        seen.add(pid)
        print(f"Stopping {label} (pid {pid})...", file=sys.stderr)
        _stop_pid(pid, timeout=timeout, use_group=use_group)
        stopped_any = True

    if not stopped_any and any_alive:
        print("Stopping socket holders...", file=sys.stderr)
    _stop_socket_holders(run_dir_path, timeout=min(timeout, 10.0))
    if not stopped_any and any_alive:
        stopped_any = True

    for pid_file in (substrate_pid_file, wrapper_pid_file):
        try:
            pid_file.unlink(missing_ok=True)
        except OSError:
            pass

    for sock_name in _SOCKET_NAMES:
        try:
            (run_dir_path / sock_name).unlink(missing_ok=True)
        except OSError:
            pass

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline and core_healthy():
        time.sleep(0.25)

    if core_healthy():
        print(
            "Warning: core still healthy on UDS — another runtime may still be running.",
            file=sys.stderr,
        )
    elif stopped_any:
        print("Runtime stopped (core + bridge).")
    else:
        print("Runtime cleaned up (processes were already stopped).")


def print_status() -> int:
    """Print runtime + bridge status. Returns shell exit code."""
    from if_security_backend.bridge.config import bridge_config_path
    from if_security_backend.bridge.runner import bridge_log_file, bridge_pid_file, is_bridge_running
    from if_security_backend.runtime.paths import bridge_socket_path

    wrapper_pid = _read_pid(supervisor_pid_file())
    substrate_pid = _read_pid(run_dir() / "supervisor.pid")
    bridge_pid = _read_pid(bridge_pid_file())
    core_ok = core_healthy()
    bridge_ok = is_bridge_running() and bridge_socket_path().exists()

    print(f"State dir:     {state_dir()}")
    print(f"Core config:   {core_config_path()}")
    print(f"Executor cfg:  {executor_config_path()}")
    print(f"Supervisor:    {supervisor_config_path()}")
    print(f"Wrapper PID:   {wrapper_pid if wrapper_pid else '(none)'}")
    if wrapper_pid is not None:
        print(f"Wrapper alive: {_pid_alive(wrapper_pid)}")
    print(f"Supervisor PID:{substrate_pid if substrate_pid else '(none)'}")
    if substrate_pid is not None:
        print(f"Supervisor alive:{_pid_alive(substrate_pid)}")
    print(f"Core healthy:  {core_ok}")
    print(f"Policy reg:    {policy_registry_healthy()}")
    print(f"Bridge socket: {bridge_socket_path()}")
    print(f"Bridge config: {bridge_config_path()}")
    print(f"Bridge PID:    {bridge_pid if bridge_pid else '(none)'}")
    print(f"Bridge running:{bridge_ok}")
    if bridge_log_file().is_file():
        print(f"Bridge log:    {bridge_log_file()}")
    if supervisor_log_file().is_file():
        print(f"Supervisor log:{supervisor_log_file()}")
    if executor_log_file().is_file():
        print(f"Executor log:  {executor_log_file()}")
    return 0 if core_ok and bridge_ok else 1


def policy_registry_healthy() -> bool:
    from if_security_backend.runtime.health import policy_registry_healthy as _pr

    return _pr()
