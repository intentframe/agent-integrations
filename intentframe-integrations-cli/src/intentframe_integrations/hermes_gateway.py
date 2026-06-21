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

from intentframe_integrations.hermes_install import bootstrap_hermes_home, resolve_hermes_bin
from intentframe_integrations.hermes_paths import hermes_home
from intentframe_integrations.integration_pack import IntegrationPack
from intentframe_integrations.adapter_lifecycle import integration_state_dir

DEFAULT_API_PORT = 8642
DEFAULT_API_HOST = "127.0.0.1"
DEFAULT_API_KEY_ENV = "INTENTFRAME_HERMES_API_KEY"


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


def is_gateway_running() -> bool:
    pid = _read_pid(gateway_pid_file())
    return pid is not None and _pid_alive(pid)


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
        env[key] = os.path.expanduser(value)
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
    if is_gateway_running():
        pid = _read_pid(gateway_pid_file())
        print(f"Hermes gateway already running (pid {pid})", file=sys.stderr)
        return pid or 0

    binary = resolve_hermes_bin()
    if binary is None:
        raise HermesGatewayError(
            "Hermes CLI not found — run: intentframe-integrations install hermes"
        )

    integration_state_dir("hermes").mkdir(parents=True, exist_ok=True)
    bootstrap_hermes_home()
    env = build_gateway_env(
        pack,
        api_server=api_server,
        api_key=api_key,
        api_port=api_port,
        api_host=api_host,
    )
    log_path = gateway_log_file()
    cmd = [str(binary), "gateway", *(gateway_args or [])]
    print(f"Starting Hermes gateway: {' '.join(cmd)}", file=sys.stderr)
    print(f"Gateway log: {log_path}", file=sys.stderr)

    log_fh = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    gateway_pid_file().write_text(str(proc.pid), encoding="utf-8")
    log_fh.close()

    if not detach:
        return proc.wait()

    if api_server:
        port = int(env.get("API_SERVER_PORT", DEFAULT_API_PORT))
        key = env.get("API_SERVER_KEY", "")
        host = env.get("API_SERVER_HOST", DEFAULT_API_HOST)
        wait_gateway_health(host=host, port=port, api_key=key)

    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if not _pid_alive(proc.pid):
            tail = _log_tail(log_path)
            raise HermesGatewayError(f"Hermes gateway exited during startup.\n{tail}")
        if api_server:
            port = int(env.get("API_SERVER_PORT", DEFAULT_API_PORT))
            key = env.get("API_SERVER_KEY", "")
            host = env.get("API_SERVER_HOST", DEFAULT_API_HOST)
            if _health_ok(host=host, port=port, api_key=key):
                print(f"Hermes gateway running (pid {proc.pid})")
                return proc.pid
        else:
            time.sleep(0.5)
            print(f"Hermes gateway running (pid {proc.pid})")
            return proc.pid
        time.sleep(0.5)

    tail = _log_tail(log_path)
    raise HermesGatewayError(f"Hermes gateway did not become ready within 15s.\n{tail}")


def stop_hermes_gateway(*, timeout: float = 15.0, quiet: bool = False) -> None:
    pid_file = gateway_pid_file()
    pid = _read_pid(pid_file)

    if pid is None or not _pid_alive(pid):
        pid_file.unlink(missing_ok=True)
        if not quiet:
            print("Hermes gateway is not running.")
        return

    if not quiet:
        print(f"Stopping Hermes gateway (pid {pid})...", file=sys.stderr)
    os.kill(pid, signal.SIGTERM)

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and _pid_alive(pid):
        time.sleep(0.25)
    if _pid_alive(pid):
        os.kill(pid, signal.SIGKILL)

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
