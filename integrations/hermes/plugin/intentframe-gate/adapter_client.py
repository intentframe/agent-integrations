"""HTTP-over-UDS client for the Hermes adapter sidecar.

Uses ``httpx`` (a Hermes core dependency) to call ``POST /validate-tool``.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx


class AdapterError(Exception):
    """Adapter HTTP or transport failure."""


@dataclass(frozen=True)
class AdapterClientConfig:
    socket_path: str
    timeout: float = 120.0

    @classmethod
    def from_env(
        cls,
        *,
        socket_env: str = "IF_AGENT_ADAPTER_SOCKET",
        default_socket: str = "~/.intentframe/integrations/hermes/adapter.sock",
    ) -> AdapterClientConfig:
        socket_path = os.environ.get(socket_env, default_socket)
        return cls(socket_path=socket_path)


def _expand_home(path: str) -> Path:
    if path.startswith("~/"):
        return Path.home() / path[2:]
    return Path(path).expanduser()


class AdapterClient:
    """Client for the Hermes adapter ``/validate-tool`` endpoint."""

    def __init__(self, config: AdapterClientConfig) -> None:
        self._config = config
        self._http: httpx.Client | None = None

    @classmethod
    def from_env(cls, **kwargs: Any) -> AdapterClient:
        return cls(AdapterClientConfig.from_env(**kwargs))

    def _ensure_http(self) -> httpx.Client:
        if self._http is None:
            socket = _expand_home(self._config.socket_path)
            if not socket.exists():
                raise FileNotFoundError(f"Adapter socket missing: {socket}")
            transport = httpx.HTTPTransport(uds=str(socket))
            self._http = httpx.Client(
                transport=transport,
                base_url="http://hermes-adapter",
                timeout=self._config.timeout,
            )
        return self._http

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    def validate_tool(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        http = self._ensure_http()
        resp = http.post(
            "/validate-tool",
            json={"tool": tool, "args": args, "context": context or {}},
        )
        try:
            body = resp.json()
        except json.JSONDecodeError as exc:
            raise AdapterError(f"Invalid JSON from adapter: {resp.text!r}") from exc
        if resp.status_code >= 400:
            detail = body.get("error") if isinstance(body, dict) else body
            raise AdapterError(f"Adapter HTTP {resp.status_code}: {detail!r}")
        if not isinstance(body, dict):
            raise AdapterError(f"Unexpected adapter response: {body!r}")
        return body
