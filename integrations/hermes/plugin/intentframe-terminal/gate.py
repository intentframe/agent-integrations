"""IntentFrame validate gate for Hermes terminal tool calls."""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol

from .adapter_client import AdapterClient, AdapterError


class ToolValidator(Protocol):
    def validate_tool(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


_session_client: AdapterClient | None = None


def reset_session_client() -> None:
    """Close and discard the module-level adapter client (tests)."""
    global _session_client
    if _session_client is not None:
        _session_client.close()
        _session_client = None


def _default_validator() -> ToolValidator:
    global _session_client
    if _session_client is None:
        _session_client = AdapterClient.from_env()
    return _session_client


def blocked_response(error: str, *, status: str = "blocked") -> str:
    return json.dumps(
        {
            "exit_code": -1,
            "error": error,
            "status": status,
        },
        ensure_ascii=False,
    )


def gate_terminal_call(
    args: dict[str, Any],
    *,
    delegate: Callable[..., str],
    validator: ToolValidator | None = None,
    **kw: Any,
) -> str:
    """Validate via Hermes adapter, then delegate to Hermes terminal_tool."""
    tool_validator = validator or _default_validator()

    try:
        result = tool_validator.validate_tool("terminal", args, context=dict(kw))
    except FileNotFoundError as exc:
        return blocked_response(str(exc), status="error")
    except AdapterError as exc:
        return blocked_response(str(exc), status="error")

    if not result.get("allowed"):
        agent_response = result.get("agent_response")
        if isinstance(agent_response, dict):
            return json.dumps(agent_response, ensure_ascii=False)
        detail = result.get("error") or "Command blocked by IntentFrame policy"
        return blocked_response(str(detail))

    terminal_args = {k: v for k, v in args.items() if k != "reason"}
    return delegate(
        command=terminal_args.get("command"),
        background=terminal_args.get("background", False),
        timeout=terminal_args.get("timeout"),
        task_id=kw.get("task_id"),
        workdir=terminal_args.get("workdir"),
        pty=terminal_args.get("pty", False),
        notify_on_complete=terminal_args.get("notify_on_complete", False),
        watch_patterns=terminal_args.get("watch_patterns"),
    )
