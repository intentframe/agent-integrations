"""Auto-gate governed tools on every registry registration (including MCP refresh)."""

from __future__ import annotations

import logging
from typing import Callable

from .gate import GATED_MARKER, wrap_handler
from .governance_loader import governed_tool_names
from .schema import inject_reason

logger = logging.getLogger(__name__)

_PATCHED_ATTR = "_intentframe_register_patched"


def install_registry_hook() -> None:
    from tools.registry import registry

    original: Callable = registry.register
    if getattr(original, _PATCHED_ATTR, False):
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
        if name in governed and not getattr(handler, GATED_MARKER, False):
            schema = inject_reason(schema, tool_name=name)
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

    setattr(patched_register, _PATCHED_ATTR, True)
    registry.register = patched_register  # type: ignore[method-assign]
