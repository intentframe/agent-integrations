"""Shared Hermes governance test infrastructure (no runtime seed required)."""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[1]
SHARED_SRC = REPO_ROOT / "integrations" / "hermes" / "shared" / "src"
TESTS_DIR = REPO_ROOT / "tests"
DEFAULT_GOVERNANCE_TEMPLATE = REPO_ROOT / "integrations" / "hermes" / "governance" / "tools.yaml"
PLUGIN_GOVERNANCE_COPY = (
    REPO_ROOT
    / "integrations"
    / "hermes"
    / "plugin"
    / "intentframe-gate"
    / "governance"
    / "tools.yaml"
)

GATEWAY_E2E_PROBE_SYMBOLS: dict[str, frozenset[str]] = {
    "terminal": frozenset({"run_allow_with_retries", "run_block_once"}),
    "write_file": frozenset(
        {"run_write_file_allow_with_retries", "run_write_file_block_once"}
    ),
    "patch": frozenset(
        {
            "run_patch_replace_allow_with_retries",
            "run_patch_replace_block_once",
            "run_patch_v4a_mixed_home_delete_semantic_with_retries",
            "run_patch_v4a_mixed_block_once",
        }
    ),
}

LIVE_PLUGIN_EXTRA_FIXTURES = frozenset(
    {"PATCH_V4A_MIXED_HOME_DELETE_ARGS", "PATCH_V4A_BLOCK_ARGS"}
)

# Generic-mapper catalog tools: live adapter/plugin semantic smoke only (no gateway LLM E2E).
# Derived from ``mapper: generic`` in the default template — do not hardcode tool names here.

_governance_env_depth = 0
_governance_env_saved: str | None = None


def default_governance_template_path() -> Path:
    return DEFAULT_GOVERNANCE_TEMPLATE


def copy_default_template(dest: Path) -> Path:
    src = default_governance_template_path()
    dest = dest.expanduser()
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return dest


def ensure_shared_loader_importable() -> None:
    if str(SHARED_SRC) not in sys.path:
        sys.path.insert(0, str(SHARED_SRC))


def ensure_plugin_loader_importable() -> None:
    plugin_tests = TESTS_DIR / "hermes_plugin"
    if str(plugin_tests) not in sys.path:
        sys.path.insert(0, str(plugin_tests))


def clear_shared_governance_cache() -> None:
    ensure_shared_loader_importable()
    from hermes_governance.loader import load_tool_catalog

    load_tool_catalog.cache_clear()


def clear_plugin_governance_cache() -> None:
    ensure_plugin_loader_importable()
    from _loader import load_plugin_module

    mod = load_plugin_module("governance_loader")
    mod.load_tool_catalog.cache_clear()


@lru_cache(maxsize=1)
def template_catalog_tool_names() -> frozenset[str]:
    ensure_shared_loader_importable()
    from hermes_governance.loader import load_tool_catalog

    return frozenset(load_tool_catalog(str(DEFAULT_GOVERNANCE_TEMPLATE)).keys())


@lru_cache(maxsize=1)
def template_generic_mapper_tool_names() -> frozenset[str]:
    """Catalog tools using ``mapper: generic`` (live semantic probes, no gateway LLM E2E)."""
    ensure_shared_loader_importable()
    from hermes_governance.loader import load_tool_catalog

    catalog = load_tool_catalog(str(DEFAULT_GOVERNANCE_TEMPLATE))
    return frozenset(name for name, spec in catalog.items() if spec.mapper == "generic")


@lru_cache(maxsize=1)
def live_semantic_probe_tool_names() -> frozenset[str]:
    """Alias for generic-mapper tools covered by live adapter/plugin semantic smoke."""
    return template_generic_mapper_tool_names()


@lru_cache(maxsize=1)
def gateway_e2e_probe_tool_names() -> frozenset[str]:
    """Native-mapper catalog tools with deterministic gateway LLM E2E probes."""
    return frozenset(GATEWAY_E2E_PROBE_SYMBOLS)


@lru_cache(maxsize=1)
def template_governed_tool_names() -> frozenset[str]:
    """Tools marked governed (yaml ``enabled: true``) in the default template."""
    ensure_shared_loader_importable()
    from hermes_governance.loader import load_governed_tools

    return frozenset(load_governed_tools(str(DEFAULT_GOVERNANCE_TEMPLATE)).keys())


# Deprecated alias — prefer template_governed_tool_names.
template_enabled_tool_names = template_governed_tool_names


def runtime_governed_tool_names() -> frozenset[str]:
    """IntentFrame-governed tools from active governance yaml (``HERMES_GOVERNANCE_YAML`` or runtime path)."""
    ensure_shared_loader_importable()
    from hermes_governance.loader import load_governed_tools

    return frozenset(load_governed_tools().keys())


@contextmanager
def governance_env(path: Path | str | None = None) -> Iterator[Path]:
    global _governance_env_depth, _governance_env_saved

    yaml_path = Path(path).expanduser() if path is not None else default_governance_template_path()
    _governance_env_depth += 1
    if _governance_env_depth == 1:
        _governance_env_saved = os.environ.get("HERMES_GOVERNANCE_YAML")
        os.environ["HERMES_GOVERNANCE_YAML"] = str(yaml_path)
        clear_shared_governance_cache()
    try:
        yield yaml_path
    finally:
        _governance_env_depth -= 1
        if _governance_env_depth == 0:
            clear_shared_governance_cache()
            if _governance_env_saved is None:
                os.environ.pop("HERMES_GOVERNANCE_YAML", None)
            else:
                os.environ["HERMES_GOVERNANCE_YAML"] = _governance_env_saved
            _governance_env_saved = None


def install_test_governance_env() -> None:
    global _governance_env_depth, _governance_env_saved

    _governance_env_depth += 1
    if _governance_env_depth == 1:
        _governance_env_saved = os.environ.get("HERMES_GOVERNANCE_YAML")
        os.environ["HERMES_GOVERNANCE_YAML"] = str(DEFAULT_GOVERNANCE_TEMPLATE)
        clear_shared_governance_cache()


def restore_test_governance_env() -> None:
    global _governance_env_depth, _governance_env_saved

    if _governance_env_depth == 0:
        return
    _governance_env_depth -= 1
    if _governance_env_depth == 0:
        clear_shared_governance_cache()
        if _governance_env_saved is None:
            os.environ.pop("HERMES_GOVERNANCE_YAML", None)
        else:
            os.environ["HERMES_GOVERNANCE_YAML"] = _governance_env_saved
        _governance_env_saved = None


class GovernanceEnvMixin(unittest.TestCase):
    """Point shared hermes-governance loader at repo default template."""

    def setUp(self) -> None:
        super().setUp()
        install_test_governance_env()

    def tearDown(self) -> None:
        restore_test_governance_env()
        super().tearDown()


class PluginGovernanceEnvMixin(unittest.TestCase):
    """Point plugin governance_loader at repo default template."""

    def setUp(self) -> None:
        super().setUp()
        ensure_plugin_loader_importable()
        from _loader import load_plugin_module

        self._governance_mod = load_plugin_module("governance_loader")
        install_test_governance_env()
        clear_plugin_governance_cache()

    def tearDown(self) -> None:
        clear_plugin_governance_cache()
        restore_test_governance_env()
        super().tearDown()
