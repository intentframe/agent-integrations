"""Load Hermes plugin modules for unit tests (no Hermes install required)."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "integrations" / "hermes" / "plugin" / "intentframe-terminal"
PKG_NAME = "intentframe_terminal_plugin"


def _ensure_package() -> types.ModuleType:
    if PKG_NAME in sys.modules:
        return sys.modules[PKG_NAME]

    pkg = types.ModuleType(PKG_NAME)
    pkg.__path__ = [str(PLUGIN_DIR)]  # type: ignore[attr-defined]
    pkg.__package__ = PKG_NAME
    sys.modules[PKG_NAME] = pkg
    return pkg


def load_plugin_module(module_name: str):
    _ensure_package()
    full_name = f"{PKG_NAME}.{module_name}"
    if full_name in sys.modules:
        return sys.modules[full_name]

    path = PLUGIN_DIR / f"{module_name}.py"
    spec = importlib.util.spec_from_file_location(full_name, path, submodule_search_locations=[])
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")

    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = PKG_NAME
    sys.modules[full_name] = mod
    spec.loader.exec_module(mod)
    return mod
