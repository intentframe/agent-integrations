"""IntentFrame validate-only gate for governed Hermes tools."""

from __future__ import annotations

from .builtin_preload import preload_governed_builtins
from .gate import wrap_handler
from .governance_loader import governed_tool_names
from .registry_hook import install_registry_hook
from .schema import inject_reason

PLUGIN_NAME = "intentframe-gate"


def register(ctx) -> None:
    """Wrap governed tools and hook future registry registrations."""
    from tools.registry import registry

    install_registry_hook()

    governed = governed_tool_names()
    preload_governed_builtins(governed)

    for entry in registry._snapshot_entries():
        if entry.name not in governed:
            continue
        ctx.register_tool(
            name=entry.name,
            toolset=entry.toolset,
            schema=inject_reason(entry.schema, tool_name=entry.name),
            handler=wrap_handler(entry.name, entry.handler, is_async=entry.is_async),
            check_fn=entry.check_fn,
            is_async=entry.is_async,
            emoji=entry.emoji or "",
            override=True,
        )
