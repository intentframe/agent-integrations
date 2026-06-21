"""Validate Hermes tools via the IntentFrame bridge."""

from __future__ import annotations

from typing import Any

from hermes_adapter.bridge_session import BridgeSession
from hermes_adapter.mapper import ValidationError, map_tool
from hermes_adapter.responses import hermes_blocked, validate_tool_response


class ValidateService:
    def __init__(self, bridge: BridgeSession | None = None) -> None:
        self._bridge = bridge or BridgeSession()

    def validate_tool(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del context
        try:
            intent = map_tool(tool, args)
        except ValidationError as exc:
            return validate_tool_response(allowed=False, error=str(exc))

        try:
            result = self._bridge.validate(intent)
        except FileNotFoundError as exc:
            return validate_tool_response(
                allowed=False,
                error=str(exc),
                status="error",
            )
        except Exception as exc:
            return validate_tool_response(
                allowed=False,
                error=f"IntentFrame bridge error: {exc}",
                status="error",
            )

        if result.get("allowed"):
            return validate_tool_response(allowed=True)

        detail = result.get("error")
        if detail is None and isinstance(result.get("data"), dict):
            detail = result["data"].get("error")
        message = str(detail) if detail else "Command blocked by IntentFrame policy"
        return validate_tool_response(allowed=False, error=message, status="blocked")

    def close(self) -> None:
        self._bridge.close()
