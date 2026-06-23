"""Import Hermes builtin modules for governed tools before registry snapshot."""

from __future__ import annotations

import importlib
import logging

logger = logging.getLogger(__name__)

# Hermes 0.17 modules that register governed tool names at import time.
# Several catalog names may share one module (write_file + patch → file_tools).
GOVERNED_BUILTIN_MODULES: dict[str, str] = {
    "terminal": "tools.terminal_tool",
    "process": "tools.process_registry",
    "write_file": "tools.file_tools",
    "patch": "tools.file_tools",
}


def preload_governed_builtins(governed: frozenset[str]) -> None:
    """Ensure governed Hermes builtins are registered before snapshot wrap."""
    seen_modules: set[str] = set()
    for tool_name in sorted(governed):
        module_name = GOVERNED_BUILTIN_MODULES.get(tool_name)
        if not module_name or module_name in seen_modules:
            continue
        seen_modules.add(module_name)
        try:
            importlib.import_module(module_name)
        except ImportError as exc:
            logger.warning(
                "IntentFrame gate: could not import %s for governed tool %s: %s",
                module_name,
                tool_name,
                exc,
            )
