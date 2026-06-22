"""No-op validate-only adapter — Guardian judges; client executes locally."""

from __future__ import annotations

from typing import Any

from executor_sdk.adapters.base import CapabilityAdapter
from executor_sdk.models import AdapterManifest, ExecutionResult

DEFAULT_SUPPORTED_ACTIONS: tuple[str, ...] = (
    "RUN_COMMAND",
    "WRITE_HOST_FILE",
    "DELETE_HOST_FILE",
)


def _parse_supported_actions(pack_options: dict[str, Any] | None) -> tuple[str, ...]:
    raw_opts = (pack_options or {}).get("validate_only")
    if raw_opts is None:
        return DEFAULT_SUPPORTED_ACTIONS
    if not isinstance(raw_opts, dict):
        raise ValueError("pack_options.validate_only must be a mapping")

    actions = raw_opts.get("supported_actions")
    if actions is None:
        return DEFAULT_SUPPORTED_ACTIONS
    if not isinstance(actions, list | tuple) or not actions:
        raise ValueError("pack_options.validate_only.supported_actions must be a non-empty list")

    parsed = tuple(str(action).strip() for action in actions)
    if not all(parsed):
        raise ValueError("pack_options.validate_only.supported_actions must be non-empty strings")
    return parsed


class ValidateOnlyAdapter(CapabilityAdapter):
    """Returns synthetic success after Guardian ALLOW (Level 2 validate-only)."""

    def __init__(self, *, pack_options: dict[str, Any] | None = None, **_kwargs) -> None:
        self._supported_actions = _parse_supported_actions(pack_options)

    async def execute(
        self,
        action: str,
        params: dict,
        credentials: dict | None = None,
    ) -> ExecutionResult:
        del credentials
        target = (
            params.get("target")
            or params.get("path")
            or params.get("command")
            or params.get("url")
        )
        return ExecutionResult(
            success=True,
            data={
                "validated_only": True,
                "action": action,
                "params": params,
                "target": target,
            },
        )

    async def rollback(self, rollback_id: str) -> ExecutionResult:
        del rollback_id
        return ExecutionResult(success=False, error="Action is irreversible")

    def supported_actions(self) -> list[str]:
        return list(self._supported_actions)

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            adapter_id="validate_only",
            name="Validate Only",
            description=(
                "No-op adapter for hybrid execution — "
                "IntentFrame judges; the agent runs the action locally."
            ),
            supported_actions=list(self._supported_actions),
            requires_credentials=False,
        )
