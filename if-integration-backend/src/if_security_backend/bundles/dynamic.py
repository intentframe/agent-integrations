"""Generic pass-through action bundle — registers action IDs from a manifest file.

Agent-agnostic: reads IF_DYNAMIC_BUNDLE_MANIFEST (path to a comma-separated list of
action IDs). If the env var is unset, this bundle registers nothing and native tools
keep working. The manifest is a static dev-shipped superset; user governance toggles
do not change it.
"""

from __future__ import annotations

import os
from pathlib import Path

from intentframe_bundle_sdk.action import ActionBundle
from intentframe_bundle_sdk.types import ActionPermission, BundleConfigError

NATIVE_ACTION_IDS = frozenset({"RUN_COMMAND", "WRITE_HOST_FILE", "DELETE_HOST_FILE"})


def parse_manifest_ids(text: str) -> frozenset[str]:
    """Parse comma-separated action IDs (tolerates whitespace and trailing commas)."""
    ids = [part.strip() for part in text.split(",") if part.strip()]
    if not ids:
        raise ValueError("manifest must contain at least one action id")
    return frozenset(ids)


class GenericDynamicBundle(ActionBundle):
    """Semantic-only bundle — no deterministic enforcement; AE + Guardian judge."""

    bundle_id = "dynamic"

    def __init__(self, action_ids: frozenset[str]) -> None:
        if not action_ids:
            raise ValueError("GenericDynamicBundle requires at least one action_id")
        overlap = action_ids & NATIVE_ACTION_IDS
        if overlap:
            raise ValueError(
                f"manifest action ids {sorted(overlap)!r} collide with native-kit; "
                "keep RUN_COMMAND, WRITE_HOST_FILE, and DELETE_HOST_FILE out of the manifest"
            )
        self.action_ids = action_ids

    def validate_constraints(self, action_permission: ActionPermission) -> None:
        if action_permission.constraints is not None:
            raise BundleConfigError(
                f"bundle {self.bundle_id!r} does not support policy constraints; "
                "use safe: false with no constraints for semantic-only actions"
            )


def register_bundles(registry) -> None:
    raw = os.environ.get("IF_DYNAMIC_BUNDLE_MANIFEST", "").strip()
    if not raw:
        return

    path = Path(raw).expanduser()
    if not path.is_file():
        raise BundleConfigError(
            f"IF_DYNAMIC_BUNDLE_MANIFEST points to missing file: {path}"
        )

    try:
        ids = parse_manifest_ids(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise BundleConfigError(str(exc)) from exc

    try:
        registry.register_action_bundle(GenericDynamicBundle(ids))
    except ValueError as exc:
        message = str(exc)
        if "duplicate action_id" in message:
            raise BundleConfigError(
                f"{message}; keep native action ids out of IF_DYNAMIC_BUNDLE_MANIFEST"
            ) from exc
        raise BundleConfigError(message) from exc
