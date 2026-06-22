"""Validate Hermes tools via the IntentFrame bridge."""

from __future__ import annotations

import logging
from typing import Any

from hermes_governance import load_governed_tools

from hermes_adapter.bridge_session import BridgeSession
from hermes_adapter.mapper import ValidationError, map_tool
from hermes_adapter.responses import validate_tool_response

logger = logging.getLogger(__name__)


def _blocked_response_for(tool: str) -> str:
    spec = load_governed_tools().get(tool)
    return spec.blocked_response if spec is not None else "generic_json"


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
                blocked_response=_blocked_response_for(tool),
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
                    blocked_response=_blocked_response_for(tool),
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
                    blocked_response=_blocked_response_for(tool),
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
                blocked_response=_blocked_response_for(tool),
            )

        return validate_tool_response(allowed=True, tool=tool)

    def close(self) -> None:
        self._bridge.close()
