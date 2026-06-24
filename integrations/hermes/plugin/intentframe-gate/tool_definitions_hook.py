"""Finalize governed tool schemas on Hermes schema composition paths.

Two hook points (see ``docs/hermes-governance-execute-code-and-schema-hooks.md``):

1. ``finalize_governed_tool_schemas`` — called from patched ``registry.get_definitions``
   for terminal, write_file, patch, cronjob, etc.

2. ``install_execute_code_schema_hook`` — patches ``build_execute_code_schema`` because
   Hermes rebuilds ``execute_code`` *after* ``get_definitions`` inside
   ``model_tools._compute_tool_definitions``, which would wipe registry-time ``reason``.

We intentionally do **not** wrap ``model_tools.get_tool_definitions`` at plugin load —
importing ``model_tools`` runs module-level ``discover_builtin_tools()`` and registers
extras like ``read_terminal``.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from .governance_loader import governed_tool_names
from .schema import inject_reason

logger = logging.getLogger(__name__)

_EXECUTE_CODE_SCHEMA_PATCHED_ATTR = "_intentframe_execute_code_schema_patched"


def finalize_governed_tool_schemas(tool_defs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure every governed tool in *tool_defs* exposes required ``reason``."""
    governed = governed_tool_names()
    if not governed:
        return tool_defs

    finalized: list[dict[str, Any]] = []
    for tool_def in tool_defs:
        if not isinstance(tool_def, dict) or tool_def.get("type") != "function":
            finalized.append(tool_def)
            continue

        function = tool_def.get("function")
        if not isinstance(function, dict):
            finalized.append(tool_def)
            continue

        name = function.get("name")
        if not isinstance(name, str) or name not in governed:
            finalized.append(tool_def)
            continue

        finalized.append({
            **tool_def,
            "function": inject_reason(function, tool_name=name),
        })
        logger.debug("IntentFrame gate finalized governed tool schema: %s", name)
    return finalized


def install_execute_code_schema_hook() -> None:
    """Inject ``reason`` after Hermes rebuilds the dynamic execute_code schema.

    Safe to patch this builder: it returns an LLM schema dict only; ``execute_code()``
    reads ``args['code']`` and ``wrap_handler`` strips ``reason`` before delegation.
    Call after ``preload_governed_builtins`` so ``tools.code_execution_tool`` is loaded.
    """
    if "execute_code" not in governed_tool_names():
        return

    from tools import code_execution_tool

    original: Callable[..., dict[str, Any]] = code_execution_tool.build_execute_code_schema
    if getattr(original, _EXECUTE_CODE_SCHEMA_PATCHED_ATTR, False):
        return

    def patched_build_execute_code_schema(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return inject_reason(original(*args, **kwargs), tool_name="execute_code")

    setattr(patched_build_execute_code_schema, _EXECUTE_CODE_SCHEMA_PATCHED_ATTR, True)
    code_execution_tool.build_execute_code_schema = patched_build_execute_code_schema  # type: ignore[method-assign]
