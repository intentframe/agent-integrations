"""Validate Hermes tools via the IntentFrame bridge."""

from __future__ import annotations

import logging
from typing import Any

from hermes_adapter.bridge_session import BridgeSession
from hermes_adapter.mapper import ValidationError, map_tool
from hermes_adapter.responses import validate_tool_response

logger = logging.getLogger(__name__)


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
            intents = map_tool(tool, args)
        except ValidationError as exc:
            logger.info("Hermes tool %r preflight blocked: %s", tool, exc)
            return validate_tool_response(
                allowed=False,
                error=str(exc),
                tool=tool,
            )

        for intent in intents:
            action = intent.get("action", "?")
            target = intent.get("target") or intent.get("path") or intent.get("command")
            target_preview = str(target)[:120] if target is not None else ""

            try:
                result = self._bridge.validate(intent)
            except FileNotFoundError as exc:
                logger.warning(
                    "Hermes tool %r action %s bridge unavailable: %s",
                    tool,
                    action,
                    exc,
                )
                return validate_tool_response(
                    allowed=False,
                    error=str(exc),
                    status="error",
                    tool=tool,
                )
            except Exception as exc:
                logger.warning(
                    "Hermes tool %r action %s bridge error: %s",
                    tool,
                    action,
                    exc,
                )
                return validate_tool_response(
                    allowed=False,
                    error=f"IntentFrame bridge error: {exc}",
                    status="error",
                    tool=tool,
                )

            if result.get("allowed"):
                logger.info(
                    "Hermes tool %r action %s ALLOW target=%r",
                    tool,
                    action,
                    target_preview,
                )
                continue

            detail = result.get("error")
            if detail is None and isinstance(result.get("data"), dict):
                detail = result["data"].get("error")
            message = (
                str(detail)
                if detail
                else f"Hermes tool {tool!r} blocked by IntentFrame policy"
            )
            logger.info(
                "Hermes tool %r action %s BLOCK target=%r reason=%s",
                tool,
                action,
                target_preview,
                message,
            )
            return validate_tool_response(
                allowed=False,
                error=message,
                status="blocked",
                tool=tool,
            )

        return validate_tool_response(allowed=True, tool=tool)

    def close(self) -> None:
        self._bridge.close()
