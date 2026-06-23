"""Resolve bundle package refs from the core profile."""

from __future__ import annotations

import yaml

from if_security_backend.runtime.paths import core_config_path


def load_core_bundle_packages() -> list[str]:
    """Return bundle entry-point short names from core.yaml (e.g. native, dynamic)."""
    path = core_config_path()
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    bundles = raw.get("bundles")
    if not isinstance(bundles, list) or not bundles:
        raise ValueError(f"core profile {path} must declare a non-empty bundles list")
    parsed = [str(item).strip() for item in bundles]
    if not all(parsed):
        raise ValueError(f"core profile {path} bundles must be non-empty strings")
    return parsed
