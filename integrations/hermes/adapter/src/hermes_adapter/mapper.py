"""Map Hermes tool calls to IntentFrame validate requests."""

from __future__ import annotations

from typing import Any


class ValidationError(ValueError):
    """Local preflight failure before calling the IntentFrame bridge."""


def validate_reason(reason: object) -> str:
    if reason is None:
        raise ValidationError("Missing required field: reason")
    if not isinstance(reason, str):
        raise ValidationError("reason must be a string")
    stripped = reason.strip()
    if not stripped:
        raise ValidationError("Missing required field: reason (empty string)")
    if len(stripped) < 3:
        raise ValidationError("reason must be at least 3 characters")
    return stripped


def map_terminal(args: dict[str, Any]) -> dict[str, Any]:
    command = args.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValidationError("Missing or invalid command")

    reason = validate_reason(args.get("reason"))
    command = command.strip()

    return {
        "action": "RUN_COMMAND",
        "command": command,
        "reason": reason,
        "target": command[:200],
    }


def map_tool(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    if tool == "terminal":
        return map_terminal(args)
    raise ValidationError(f"Unsupported tool for validation: {tool!r}")
