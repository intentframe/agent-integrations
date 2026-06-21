"""HTTP-over-UDS client for POST /handshake and POST /validate."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from if_integration_bridge.errors import BridgeHttpError


def _expand_home(path: str) -> Path:
    if path.startswith("~/"):
        return Path.home() / path[2:]
    return Path(path).expanduser()


@dataclass(frozen=True)
class BridgeClientConfig:
    socket_path: str
    secret: str
    timeout: float = 120.0

    @classmethod
    def from_env(
        cls,
        *,
        socket_env: str = "IF_SECURITY_BRIDGE_SOCKET",
        secret_env: str = "IF_AGENT_BRIDGE_SECRET",
        default_socket: str = "~/.intentframe/backend/bridge.sock",
    ) -> BridgeClientConfig:
        secret = os.environ.get(secret_env)
        if not secret:
            raise ValueError(f"{secret_env} is required")
        socket_path = os.environ.get(socket_env, default_socket)
        return cls(socket_path=socket_path, secret=secret)


class BridgeClient:
    """Jarvis-style session: handshake once, then validate."""

    def __init__(self, config: BridgeClientConfig) -> None:
        self._config = config
        self._http: httpx.Client | None = None
        self.runtime_context: dict[str, Any] | None = None

    @classmethod
    def from_env(cls, **kwargs: Any) -> BridgeClient:
        return cls(BridgeClientConfig.from_env(**kwargs))

    def _ensure_http(self) -> httpx.Client:
        if self._http is None:
            socket = _expand_home(self._config.socket_path)
            if not socket.exists():
                raise FileNotFoundError(f"Bridge socket missing: {socket}")
            transport = httpx.HTTPTransport(uds=str(socket))
            self._http = httpx.Client(
                transport=transport,
                base_url="http://bridge",
                timeout=self._config.timeout,
                headers={"Authorization": f"Bearer {self._config.secret}"},
            )
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def __enter__(self) -> BridgeClient:
        self._ensure_http()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def handshake(self, capabilities: dict[str, Any] | None = None) -> dict[str, Any]:
        http = self._ensure_http()
        resp = http.post("/handshake", json=capabilities or {})
        body = resp.json()
        if resp.status_code >= 400:
            raise BridgeHttpError(resp.status_code, body)
        self.runtime_context = body
        return body

    def validate(self, request: dict[str, Any]) -> dict[str, Any]:
        http = self._ensure_http()
        resp = http.post("/validate", json=request)
        body = resp.json()
        if resp.status_code >= 400:
            raise BridgeHttpError(resp.status_code, body)
        return body

    def validate_run_command(
        self,
        *,
        command: str,
        reason: str,
        target: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        req: dict[str, Any] = {
            "action": "RUN_COMMAND",
            "command": command,
            "reason": reason,
            "target": target if target is not None else command[:200],
            **extra,
        }
        return self.validate(req)

    def validate_raw(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        """Return (status_code, body) without raising on HTTP errors."""
        http = self._ensure_http()
        resp = http.post("/validate", json=request)
        return resp.status_code, resp.json()

    def validate_expect_status(
        self,
        request: dict[str, Any],
        *,
        status_code: int,
    ) -> dict[str, Any]:
        code, body = self.validate_raw(request)
        if code != status_code:
            raise BridgeHttpError(code, body, expected=status_code)
        return body
