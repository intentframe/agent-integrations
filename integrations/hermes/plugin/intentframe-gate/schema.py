"""Inject required ``reason`` into governed tool schemas."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

_REASON_PROPERTY: dict[str, Any] = {
    "type": "string",
    "description": (
        "Why you are invoking this tool and what outcome you expect. "
        "Required for security policy review before execution."
    ),
}

_REASON_SUFFIX = (
    "\n\nYou MUST provide `reason`: a short explanation of why this "
    "tool call is needed and what it will do."
)


def inject_reason(schema: dict[str, Any], *, tool_name: str) -> dict[str, Any]:
    """Return a deep copy of *schema* with required ``reason`` (idempotent)."""
    out = deepcopy(schema)
    params = out.setdefault("parameters", {})
    if not isinstance(params, dict):
        params = {"type": "object", "properties": {}}
        out["parameters"] = params

    params.setdefault("type", "object")
    props = params.setdefault("properties", {})
    if not isinstance(props, dict):
        props = {}
        params["properties"] = props

    if tool_name == "terminal":
        props["reason"] = {
            "type": "string",
            "description": (
                "Why you are running this command and what outcome you expect. "
                "Required for security policy review before execution."
            ),
        }
        reason_suffix = (
            "\n\nYou MUST provide `reason`: a short explanation of why this "
            "command is needed and what it will do."
        )
    else:
        props["reason"] = deepcopy(_REASON_PROPERTY)
        reason_suffix = _REASON_SUFFIX

    required = list(params.get("required") or [])
    if "reason" not in required:
        required.append("reason")
    params["required"] = required

    description = out.get("description") or ""
    if reason_suffix not in description:
        out["description"] = description + reason_suffix

    return out
