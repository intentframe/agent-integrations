"""Shared governed-tool contract for Hermes IntentFrame integration."""

from hermes_governance.loader import (
    ToolSpec,
    governance_catalog_names,
    governed_tool_names,
    load_governed_tools,
    load_tool_catalog,
    supported_actions,
    supported_tools,
)

__all__ = [
    "ToolSpec",
    "governance_catalog_names",
    "governed_tool_names",
    "load_governed_tools",
    "load_tool_catalog",
    "supported_actions",
    "supported_tools",
]
