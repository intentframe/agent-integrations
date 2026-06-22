"""Shared governed-tool contract for Hermes IntentFrame integration."""

from hermes_governance.loader import (
    ToolSpec,
    governed_tool_names,
    load_governed_tools,
    supported_actions,
    supported_tools,
)

__all__ = [
    "ToolSpec",
    "governed_tool_names",
    "load_governed_tools",
    "supported_actions",
    "supported_tools",
]
