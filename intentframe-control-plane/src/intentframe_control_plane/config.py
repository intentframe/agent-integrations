"""Control plane configuration from environment and ~/.intentframe/.env."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9720

INTENTFRAME_HOME = Path.home() / ".intentframe"
ENV_FILE = INTENTFRAME_HOME / ".env"
PID_FILE = INTENTFRAME_HOME / "control-plane.pid"  # uvicorn PID from control-plane start
LOG_FILE = INTENTFRAME_HOME / "logs" / "control-plane.log"
SERVER_LOG = INTENTFRAME_HOME / "logs" / "intentframe-server.log"
POLICY_RUNTIME = INTENTFRAME_HOME / "integrations" / "hermes" / "policy.yaml"
BRIDGE_SOCKET = INTENTFRAME_HOME / "backend" / "bridge.sock"


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


def load_dotenv() -> None:
    for key, value in _parse_env_file(ENV_FILE).items():
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class ControlPlaneSettings:
    host: str
    port: int
    token: str | None
    allow_remote: bool

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @classmethod
    def from_env(cls) -> ControlPlaneSettings:
        load_dotenv()
        host = os.environ.get("INTENTFRAME_CONTROL_PLANE_HOST", DEFAULT_HOST)
        port_raw = os.environ.get("INTENTFRAME_CONTROL_PLANE_PORT", str(DEFAULT_PORT))
        token = os.environ.get("INTENTFRAME_CONTROL_PLANE_TOKEN") or None
        allow_remote = os.environ.get("INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE", "").lower() in {
            "1",
            "true",
            "yes",
        }
        return cls(
            host=host,
            port=int(port_raw),
            token=token,
            allow_remote=allow_remote,
        )


def validate_bind_host(host: str, *, allow_remote: bool) -> None:
    if host in ("127.0.0.1", "localhost", "::1"):
        return
    if allow_remote:
        return
    raise ValueError(
        f"Refusing to bind control plane to {host!r}. "
        "Use 127.0.0.1 or set INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE=1."
    )
