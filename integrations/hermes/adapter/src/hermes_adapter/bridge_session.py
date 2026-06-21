"""Long-lived bridge client session for the adapter process."""

from __future__ import annotations

from typing import Any

from if_integration_bridge import BridgeClient
from if_integration_bridge.errors import BridgeHttpError


class BridgeSession:
    """Handshake once per adapter process, then validate."""

    def __init__(self) -> None:
        self._client = BridgeClient.from_env()
        self._handshaked = False

    def close(self) -> None:
        self._client.close()

    def validate(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self._handshaked:
            self._client.handshake()
            self._handshaked = True
        try:
            return self._client.validate(request)
        except BridgeHttpError as exc:
            if exc.status_code == 412:
                self._client.handshake()
                self._handshaked = True
                return self._client.validate(request)
            raise

    def validate_run_command(self, *, command: str, reason: str) -> dict[str, Any]:
        return self.validate(
            {
                "action": "RUN_COMMAND",
                "command": command,
                "reason": reason,
                "target": command[:200],
            }
        )
