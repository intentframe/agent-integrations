"""Start/stop Hermes gateway under orchestrator control."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from intentframe_integrations.hermes_governance_contract import ensure_runtime_governance_yaml
from intentframe_integrations.hermes_install import bootstrap_hermes_home, resolve_hermes_bin
from intentframe_integrations.hermes_paths import hermes_home
from intentframe_integrations.integration_pack import IntegrationPack
from intentframe_integrations.adapter_lifecycle import integration_state_dir

DEFAULT_API_PORT = 8642
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_KEY_ENV = "INTENTFRAME_HERMES_API_KEY"
HERMES_GATEWAY_SERVICE_SUBCOMMANDS = frozenset(
    {
        "start",
        "stop",
        "restart",
        "status",
        "install",
        "uninstall",
        "list",
        "setup",
        "migrate-legacy",
        "enroll",
    }
)
HERMES_GATEWAY_RUN_FLAGS = frozenset(
    {
        "-v",
        "-vv",
        "-vvv",
        "--verbose",
        "-q",
        "--quiet",
        "--replace",
        "--force",
        "--no-supervise",
        "--accept-hooks",
    }
)
DEFAULT_HERMES_GATEWAY_COMMAND = "run"


class HermesGatewayError(Exception):
    pass


def gateway_pid_file() -> Path:
    return integration_state_dir("hermes") / "gateway.pid"


def gateway_log_file() -> Path:
    return integration_state_dir("hermes") / "gateway.log"


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


def _pid_command(pid: int) -> str | None:
    if os.name == "nt":
        return None
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    cmd = result.stdout.strip()
    return cmd or None


def _pid_is_hermes_gateway(pid: int, *, binary: Path | None = None) -> bool:
    cmd = _pid_command(pid)
    if cmd is None:
        return _pid_alive(pid)
    if "gateway" not in cmd:
        return False
    if binary is not None and str(binary) in cmd:
        return True
    return "hermes" in Path(cmd.split()[0]).name.lower()


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


def _terminate_process_group(pid: int) -> None:
    if os.name == "nt":
        _terminate_pid(pid)
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        _terminate_pid(pid)


def _kill_process_group(pid: int) -> None:
    if os.name == "nt":
        _kill_pid(pid)
        return
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        _kill_pid(pid)


def is_gateway_running(*, binary: Path | None = None) -> bool:
    pid = _read_pid(gateway_pid_file())
    if pid is None:
        return False
    if not _pid_alive(pid):
        return False
    if not _pid_is_hermes_gateway(pid, binary=binary):
        gateway_pid_file().unlink(missing_ok=True)
        return False
    return True


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_env_file(path: Path, updates: dict[str, str]) -> None:
    existing = _parse_env_file(path)
    existing.update(updates)
    lines = [f"{key}={value}" for key, value in existing.items()]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def normalize_hermes_gateway_argv(gateway_args: list[str] | None) -> list[str]:
    """Map orchestrator args to ``hermes gateway run`` (foreground process runner).

    Upstream ``hermes gateway start|stop|...`` are OS service-manager commands.
    IntentFrame-managed lifecycle always invokes ``gateway run`` with run flags only.
    """
    args = list(gateway_args or [])
    if args and args[0] in HERMES_GATEWAY_SERVICE_SUBCOMMANDS:
        args = args[1:]
    run_args: list[str] = []
    for arg in args:
        if arg in HERMES_GATEWAY_RUN_FLAGS:
            run_args.append(arg)
        elif arg == DEFAULT_HERMES_GATEWAY_COMMAND:
            continue
    return [DEFAULT_HERMES_GATEWAY_COMMAND, *run_args]


def ensure_api_server_config(
    *,
    api_key: str | None = None,
    port: int | None = None,
    host: str | None = None,
) -> dict[str, str]:
    """Write API server settings to HERMES_HOME/.env."""
    home = bootstrap_hermes_home()
    env_path = home / ".env"
    key = api_key or os.environ.get(DEFAULT_API_KEY_ENV) or os.environ.get("API_SERVER_KEY")
    if not key:
        key = "intentframe-local-dev-key"
    port_value = str(port if port is not None else int(os.environ.get("API_SERVER_PORT", DEFAULT_API_PORT)))
    host_value = host or os.environ.get("API_SERVER_HOST", DEFAULT_API_HOST)
    updates = {
        "API_SERVER_ENABLED": "true",
        "API_SERVER_KEY": key,
        "API_SERVER_PORT": port_value,
        "API_SERVER_HOST": host_value,
    }
    _write_env_file(env_path, updates)
    return updates


def build_gateway_env(
    pack: IntegrationPack,
    *,
    api_server: bool = False,
    api_key: str | None = None,
    api_port: int | None = None,
    api_host: str | None = None,
) -> dict[str, str]:
    env = os.environ.copy()
    env["HERMES_HOME"] = str(hermes_home())
    for key, value in pack.agent.env.items():
        env.setdefault(key, os.path.expanduser(value))
    if api_server:
        api_cfg = ensure_api_server_config(api_key=api_key, port=api_port, host=api_host)
        env.update(api_cfg)
    return env


def start_hermes_gateway(
    pack: IntegrationPack,
    *,
    detach: bool = True,
    api_server: bool = False,
    api_key: str | None = None,
    api_port: int | None = None,
    api_host: str | None = None,
    gateway_args: list[str] | None = None,
) -> int:
    binary = resolve_hermes_bin()
    if is_gateway_running(binary=binary):
        pid = _read_pid(gateway_pid_file())
        print(f"Hermes gateway already running (pid {pid})", file=sys.stderr)
        return pid or 0

    if binary is None:
        raise HermesGatewayError(
            "Hermes CLI not found — run: intentframe-integrations install hermes"
        )

    integration_state_dir("hermes").mkdir(parents=True, exist_ok=True)
    bootstrap_hermes_home()
    ensure_runtime_governance_yaml("hermes")
    env = build_gateway_env(
        pack,
        api_server=api_server,
        api_key=api_key,
        api_port=api_port,
        api_host=api_host,
    )
    log_path = gateway_log_file()
    gateway_argv = normalize_hermes_gateway_argv(gateway_args)
    cmd = [str(binary), "gateway", *gateway_argv]
    print(f"Starting Hermes gateway: {' '.join(cmd)}", file=sys.stderr)
    print(f"Gateway log: {log_path}", file=sys.stderr)

    log_fh = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        **_process_group_kwargs(),
    )
    gateway_pid_file().write_text(str(proc.pid), encoding="utf-8")
    log_fh.close()

    if not detach:
        return proc.wait()

    port = int(env.get("API_SERVER_PORT", DEFAULT_API_PORT)) if api_server else None
    key = env.get("API_SERVER_KEY", "") if api_server else ""
    host = env.get("API_SERVER_HOST", DEFAULT_API_HOST) if api_server else DEFAULT_API_HOST
    ready_timeout = 30.0 if api_server else 15.0
    deadline = time.monotonic() + ready_timeout
    while time.monotonic() < deadline:
        if not _pid_alive(proc.pid):
            tail = _log_tail(log_path)
            raise HermesGatewayError(f"Hermes gateway exited during startup.\n{tail}")
        if api_server and port is not None and _health_ok(host=host, port=port, api_key=key):
            print(f"Hermes gateway running (pid {proc.pid})")
            return proc.pid
        if not api_server:
            time.sleep(0.5)
            print(f"Hermes gateway running (pid {proc.pid})")
            return proc.pid
        time.sleep(0.5)

    tail = _log_tail(log_path)
    if api_server and port is not None:
        detail = f"health check failed at http://{host}:{port}/health"
    else:
        detail = "process did not become ready"
    raise HermesGatewayError(
        f"Hermes gateway did not become ready within {ready_timeout:.0f}s ({detail}).\n{tail}"
    )


def stop_hermes_gateway(*, timeout: float = 15.0, quiet: bool = False) -> None:
    pid_file = gateway_pid_file()
    pid = _read_pid(pid_file)

    binary = resolve_hermes_bin()
    if pid is None or not _pid_alive(pid):
        pid_file.unlink(missing_ok=True)
        if not quiet:
            print("Hermes gateway is not running.")
        return

    if not _pid_is_hermes_gateway(pid, binary=binary):
        pid_file.unlink(missing_ok=True)
        if not quiet:
            print("Hermes gateway is not running (stale pid file).")
        return

    if not quiet:
        print(f"Stopping Hermes gateway (pid {pid})...", file=sys.stderr)
    _terminate_process_group(pid)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.25)
    if _pid_alive(pid):
        _kill_process_group(pid)

    pid_file.unlink(missing_ok=True)
    if not quiet:
        print("Hermes gateway stopped.")


def _log_tail(path: Path, *, max_chars: int = 2000) -> str:
    try:
        return path.read_text(encoding="utf-8")[-max_chars:]
    except OSError:
        return ""


def _health_ok(*, host: str, port: int, api_key: str) -> bool:
    url = f"http://{host}:{port}/health"
    req = urllib.request.Request(url)
    if api_key:
        req.add_header("Authorization", f"Bearer {api_key}")
    try:
        with urllib.request.urlopen(req, timeout=2) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError):
        return False


def wait_gateway_health(
    *,
    host: str = DEFAULT_API_HOST,
    port: int = DEFAULT_API_PORT,
    api_key: str = "",
    timeout: float = 30.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _health_ok(host=host, port=port, api_key=api_key):
            return
        time.sleep(0.5)
    raise HermesGatewayError(f"Gateway health check failed at http://{host}:{port}/health")
