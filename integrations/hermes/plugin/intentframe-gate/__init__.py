"""IntentFrame validate-only gate for governed Hermes tools."""

from __future__ import annotations

from .builtin_preload import preload_governed_builtins
from .gate import wrap_handler
from .governance_loader import load_governed_tools
from .registry_hook import install_registry_hook
from .tool_definitions_hook import install_execute_code_schema_hook

PLUGIN_NAME = "intentframe-gate"


def register(ctx) -> None:
    """Wrap governed tools and hook future registry registrations.

    Load order matters — see ``docs/hermes-governance-execute-code-and-schema-hooks.md``:

    1. Registry hooks (handler gate + get_definitions schema finalization).
       Must NOT import ``model_tools`` (triggers full ``discover_builtin_tools()``).
    2. Selective preload of governed ``builtin_module`` entries only.
    3. ``execute_code`` builder hook (dynamic schema rebuild path).
    4. Snapshot handler wrap — schemas finalized on get_definitions, not here.
    """
    from tools.registry import registry

    install_registry_hook()

    governed_tools = load_governed_tools()
    governed = frozenset(governed_tools)
    preload_governed_builtins(governed_tools)
    install_execute_code_schema_hook()

    for entry in registry._snapshot_entries():
        if entry.name not in governed:
            continue
        ctx.register_tool(
            name=entry.name,
            toolset=entry.toolset,
            schema=entry.schema,
            handler=wrap_handler(entry.name, entry.handler, is_async=entry.is_async),
            check_fn=entry.check_fn,
            is_async=entry.is_async,
            emoji=entry.emoji or "",
            override=True,
        )
