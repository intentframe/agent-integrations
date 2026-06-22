"""IntentFrame validate gate for governed Hermes tool calls."""

from __future__ import annotations

import json
from typing import Any, Callable, Protocol

from .adapter_client import AdapterClient, AdapterError
from .governance_loader import ToolSpec, load_governed_tools

GATED_MARKER = "__intentframe_gated__"


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


def blocked_response(
    error: str,
    *,
    spec: ToolSpec | None = None,
    status: str = "blocked",
    result: dict[str, Any] | None = None,
) -> str:
    if result is not None:
        agent_response = result.get("agent_response")
        if isinstance(agent_response, dict):
            return json.dumps(agent_response, ensure_ascii=False)

    if spec is not None and spec.blocked_response == "terminal_json":
        return json.dumps(
            {"exit_code": -1, "error": error, "status": status},
            ensure_ascii=False,
        )

    return json.dumps({"status": status, "error": error}, ensure_ascii=False)


def gate_tool_call(
    tool_name: str,
    args: dict[str, Any],
    *,
    delegate: Callable[..., Any],
    validator: ToolValidator | None = None,
    is_async: bool = False,
    **kw: Any,
) -> Any:
    """Validate via Hermes adapter, then delegate to the original handler."""
    del is_async
    tool_validator = validator or _default_validator()
    spec = load_governed_tools().get(tool_name)

    try:
        result = tool_validator.validate_tool(tool_name, args, context=dict(kw))
    except FileNotFoundError as exc:
        return blocked_response(str(exc), spec=spec, status="error")
    except AdapterError as exc:
        return blocked_response(str(exc), spec=spec, status="error")

    if not result.get("allowed"):
        detail = result.get("error") or "Tool call blocked by IntentFrame policy"
        return blocked_response(str(detail), spec=spec, result=result)

    clean_args = {k: v for k, v in args.items() if k != "reason"}
    return delegate(clean_args, **kw)


async def gate_tool_call_async(
    tool_name: str,
    args: dict[str, Any],
    *,
    delegate: Callable[..., Any],
    validator: ToolValidator | None = None,
    **kw: Any,
) -> Any:
    tool_validator = validator or _default_validator()
    spec = load_governed_tools().get(tool_name)

    try:
        result = tool_validator.validate_tool(tool_name, args, context=dict(kw))
    except FileNotFoundError as exc:
        return blocked_response(str(exc), spec=spec, status="error")
    except AdapterError as exc:
        return blocked_response(str(exc), spec=spec, status="error")

    if not result.get("allowed"):
        detail = result.get("error") or "Tool call blocked by IntentFrame policy"
        return blocked_response(str(detail), spec=spec, result=result)

    clean_args = {k: v for k, v in args.items() if k != "reason"}
    return await delegate(clean_args, **kw)


def wrap_handler(
    tool_name: str,
    original: Callable[..., Any],
    *,
    is_async: bool,
) -> Callable[..., Any]:
    if getattr(original, GATED_MARKER, False):
        return original

    if is_async:

        async def async_handler(args: dict[str, Any], **kw: Any) -> Any:
            return await gate_tool_call_async(
                tool_name,
                args,
                delegate=original,
                is_async=True,
                **kw,
            )

        setattr(async_handler, GATED_MARKER, True)
        return async_handler

    def sync_handler(args: dict[str, Any], **kw: Any) -> Any:
        return gate_tool_call(
            tool_name,
            args,
            delegate=original,
            is_async=False,
            **kw,
        )

    setattr(sync_handler, GATED_MARKER, True)
    return sync_handler
