"""No-op RUN_COMMAND adapter — Guardian judges; client executes locally."""

from __future__ import annotations

from executor_sdk.adapters.base import CapabilityAdapter
from executor_sdk.models import AdapterManifest, ExecutionResult


class ValidateOnlyAdapter(CapabilityAdapter):
    """Returns synthetic success after Guardian ALLOW (Level 2 validate-only)."""

    def __init__(self, **_kwargs) -> None:
        pass

    async def execute(
        self,
        action: str,
        params: dict,
        credentials: dict | None = None,
    ) -> ExecutionResult:
        del credentials
        command = str(params.get("command", ""))
        return ExecutionResult(
            success=True,
            data={
                "validated_only": True,
                "action": action,
                "command": command,
            },
        )

    async def rollback(self, rollback_id: str) -> ExecutionResult:
        del rollback_id
        return ExecutionResult(success=False, error="Action is irreversible")

    def supported_actions(self) -> list[str]:
        return ["RUN_COMMAND"]

    def manifest(self) -> AdapterManifest:
        return AdapterManifest(
            adapter_id="validate_only",
            name="Validate Only",
            description=(
                "No-op RUN_COMMAND for hybrid execution — "
                "IntentFrame judges; the agent runs the action locally."
            ),
            supported_actions=["RUN_COMMAND"],
            requires_credentials=False,
        )
