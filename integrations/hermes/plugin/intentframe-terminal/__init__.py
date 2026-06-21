"""IntentFrame validate-only override for Hermes ``terminal`` tool."""

from __future__ import annotations

from .gate import gate_terminal_call
from .schema import build_terminal_schema

PLUGIN_NAME = "intentframe-terminal"


def _terminal_check_fn():
    try:
        from tools.terminal_tool import check_terminal_requirements

        return check_terminal_requirements
    except ImportError:
        return lambda: True


def _terminal_delegate(**kwargs):
    from tools.terminal_tool import terminal_tool

    return terminal_tool(**kwargs)


def _handle_terminal(args, **kw):
    return gate_terminal_call(args, delegate=_terminal_delegate, **kw)


def register(ctx) -> None:
    schema = build_terminal_schema()
    ctx.register_tool(
        name="terminal",
        toolset="terminal",
        schema=schema,
        handler=_handle_terminal,
        check_fn=_terminal_check_fn(),
        override=True,
        emoji="💻",
    )
