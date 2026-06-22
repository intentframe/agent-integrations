"""Shape validate results for Hermes tool handlers."""

from __future__ import annotations

from typing import Any


def hermes_blocked(error: str, *, status: str = "blocked") -> dict[str, Any]:
    return {
        "exit_code": -1,
        "error": error,
        "status": status,
    }


def generic_blocked(error: str, *, status: str = "blocked") -> dict[str, Any]:
    return {
        "status": status,
        "error": error,
    }


def validate_tool_response(
    *,
    allowed: bool,
    error: str | None = None,
    status: str = "blocked",
    tool: str | None = None,
    blocked_response: str = "generic_json",
) -> dict[str, Any]:
    if allowed:
        return {"allowed": True}

    default_message = (
        f"Hermes tool {tool!r} blocked by IntentFrame policy"
        if tool
        else "Tool call blocked by IntentFrame policy"
    )
    message = error or default_message

    if blocked_response == "terminal_json":
        agent_response = hermes_blocked(message, status=status)
    else:
        agent_response = generic_blocked(message, status=status)

    return {
        "allowed": False,
        "error": message,
        "agent_response": agent_response,
    }
