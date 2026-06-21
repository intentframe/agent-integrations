"""Generic validate-only executor pack for hybrid agents (RUN_COMMAND today).

One pack serves every agent (Hermes, OpenClaw, …). Agents never ship executor
packs — they call the bridge, execute locally after ALLOW.
"""

from __future__ import annotations

from executor_sdk.adapters import register_adapter

from if_security_backend.executor_pack.validate_adapter import ValidateOnlyAdapter

__all__ = ["ValidateOnlyAdapter", "register_all"]


def register_all() -> None:
    """Register the validate-only RUN_COMMAND adapter."""
    register_adapter("validate_only", ValidateOnlyAdapter)
