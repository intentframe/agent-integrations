"""Import Hermes builtin modules for governed tools before registry snapshot."""

from __future__ import annotations

import importlib
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .governance_loader import ToolSpec

logger = logging.getLogger(__name__)


def preload_governed_builtins(governed_tools: dict[str, "ToolSpec"]) -> None:
    """Ensure governed Hermes builtins are registered before snapshot wrap.

    Imports ``builtin_module`` from each enabled governed tool spec (yaml, dev-owned).
    Disabled catalog entries are not in *governed_tools* and are never preloaded.
    """
    seen_modules: set[str] = set()
    for tool_name in sorted(governed_tools):
        module_name = governed_tools[tool_name].builtin_module
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
