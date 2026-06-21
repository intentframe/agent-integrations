"""Shape validate results for Hermes tool handlers."""

from __future__ import annotations

from typing import Any


def hermes_blocked(error: str, *, status: str = "blocked") -> dict[str, Any]:
    return {
        "exit_code": -1,
        "error": error,
        "status": status,
    }


def validate_tool_response(
    *,
    allowed: bool,
    error: str | None = None,
    status: str = "blocked",
) -> dict[str, Any]:
    if allowed:
        return {"allowed": True}
    message = error or "Command blocked by IntentFrame policy"
    return {
        "allowed": False,
        "error": message,
        "agent_response": hermes_blocked(message, status=status),
    }
