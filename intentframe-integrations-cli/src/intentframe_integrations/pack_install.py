"""Integration pack install provenance (written by install-hermes-plugin.sh)."""

from __future__ import annotations

import json
import os
from pathlib import Path

INSTALL_MANIFEST_NAME = ".install-manifest.json"


def pack_install_dir() -> Path:
    root = os.environ.get("INTENTFRAME_INTEGRATIONS_ROOT")
    if root:
        return Path(root)
    return Path.home() / ".intentframe" / "agent-integrations"


def pack_install_manifest_path() -> Path:
    return pack_install_dir() / INSTALL_MANIFEST_NAME


def load_pack_install_manifest() -> dict | None:
    path = pack_install_manifest_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return raw if isinstance(raw, dict) else None


def pack_install_status_lines() -> tuple[str, ...]:
    path = pack_install_manifest_path()
    data = load_pack_install_manifest()
    if data is None:
        if path.is_file():
            return (f"  integration pack: manifest unreadable ({path})",)
        return (f"  integration pack: {pack_install_dir()} (no install manifest)",)

    ref = data.get("ref")
    installed_at = data.get("installed_at")
    parts: list[str] = []
    if isinstance(ref, str) and ref:
        parts.append(f"ref {ref}")
    if isinstance(installed_at, str) and installed_at:
        parts.append(f"installed {installed_at}")
    if parts:
        return (f"  integration pack: {', '.join(parts)} ({pack_install_dir()})",)
    return (f"  integration pack: {pack_install_dir()}",)
