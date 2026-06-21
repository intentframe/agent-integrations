"""Terminal tool schema with required ``reason`` for IntentFrame policy review."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_REASON_PROPERTY: dict[str, Any] = {
    "type": "string",
    "description": (
        "Why you are running this command and what outcome you expect. "
        "Required for security policy review before execution."
    ),
}

_REASON_SUFFIX = (
    "\n\nYou MUST provide `reason`: a short explanation of why this "
    "command is needed and what it will do."
)

# Fallback when Hermes is not installed (tests / static analysis).
_FALLBACK_DESCRIPTION = (
    "Execute shell commands in the configured terminal environment."
    + _REASON_SUFFIX
)

_FALLBACK_SCHEMA: dict[str, Any] = {
    "name": "terminal",
    "description": _FALLBACK_DESCRIPTION,
    "parameters": {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The command to execute",
            },
            "reason": _REASON_PROPERTY,
            "background": {
                "type": "boolean",
                "description": "Run the command in the background.",
                "default": False,
            },
            "timeout": {
                "type": "integer",
                "description": "Max seconds to wait for the command.",
                "minimum": 1,
            },
            "workdir": {
                "type": "string",
                "description": "Working directory for this command (absolute path).",
            },
            "pty": {
                "type": "boolean",
                "description": "Run in pseudo-terminal (PTY) mode.",
                "default": False,
            },
            "notify_on_complete": {
                "type": "boolean",
                "description": "When true and background=true, notify when the process exits.",
                "default": False,
            },
            "watch_patterns": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Strings to watch for in background process output.",
            },
        },
        "required": ["command", "reason"],
    },
}


def build_terminal_schema() -> dict[str, Any]:
    """Extend live Hermes TERMINAL_SCHEMA with required ``reason`` when available."""
    try:
        from tools.terminal_tool import TERMINAL_SCHEMA, TERMINAL_TOOL_DESCRIPTION
    except ImportError:
        return deepcopy(_FALLBACK_SCHEMA)

    schema = deepcopy(TERMINAL_SCHEMA)
    params = schema.setdefault("parameters", {})
    props = params.setdefault("properties", {})
    props["reason"] = deepcopy(_REASON_PROPERTY)

    required = list(params.get("required") or ["command"])
    if "reason" not in required:
        required.append("reason")
    params["required"] = required

    description = schema.get("description") or TERMINAL_TOOL_DESCRIPTION
    if _REASON_SUFFIX not in description:
        schema["description"] = description + _REASON_SUFFIX

    return schema
