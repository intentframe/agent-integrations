"""Auto-gate governed tools on every registry registration (including MCP refresh).

Also finalizes model-facing schemas on ``registry.get_definitions`` (injects required
``reason`` for governed tools).

Do **not** import ``model_tools`` here — Hermes runs ``discover_builtin_tools()`` at
``model_tools`` import time, which leaks desktop-only tools like ``read_terminal`` into
the terminal toolset before the gateway's intended lazy load order.

See ``docs/hermes-governance-execute-code-and-schema-hooks.md``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .gate import GATED_MARKER, wrap_handler
from .governance_loader import governed_tool_names
from .tool_definitions_hook import finalize_governed_tool_schemas

logger = logging.getLogger(__name__)

_REGISTER_PATCHED_ATTR = "_intentframe_register_patched"
_GET_DEFINITIONS_PATCHED_ATTR = "_intentframe_get_definitions_patched"


def install_registry_hook() -> None:
    from tools.registry import registry

    _install_register_hook(registry)
    _install_get_definitions_hook(registry)


def _install_register_hook(registry: Any) -> None:
    original: Callable = registry.register
    if getattr(original, _REGISTER_PATCHED_ATTR, False):
        return

    governed = governed_tool_names()

    def patched_register(
        name: str,
        toolset: str,
        schema: dict,
        handler: Callable,
        check_fn: Callable = None,
        requires_env: list = None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        max_result_size_chars: int | float | None = None,
        dynamic_schema_overrides: Callable = None,
        override: bool = False,
    ):
        # Schema finalization is on get_definitions / builder hooks — not here.
        # execute_code schema is rebuilt by Hermes after get_definitions anyway.
        if name in governed and not getattr(handler, GATED_MARKER, False):
            handler = wrap_handler(name, handler, is_async=is_async)
            logger.debug("IntentFrame gate applied to registry registration: %s", name)
        return original(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env,
            is_async=is_async,
            description=description,
            emoji=emoji,
            max_result_size_chars=max_result_size_chars,
            dynamic_schema_overrides=dynamic_schema_overrides,
            override=override,
        )

    setattr(patched_register, _REGISTER_PATCHED_ATTR, True)
    registry.register = patched_register  # type: ignore[method-assign]


def _install_get_definitions_hook(registry: Any) -> None:
    """Inject ``reason`` into governed tool schemas on the LLM payload path."""
    original: Callable[..., list[dict[str, Any]]] = registry.get_definitions
    if getattr(original, _GET_DEFINITIONS_PATCHED_ATTR, False):
        return

    def patched_get_definitions(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return finalize_governed_tool_schemas(original(*args, **kwargs))

    setattr(patched_get_definitions, _GET_DEFINITIONS_PATCHED_ATTR, True)
    registry.get_definitions = patched_get_definitions  # type: ignore[method-assign]
