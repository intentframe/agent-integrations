#!/usr/bin/env python3
"""Unit tests for hermes-governance contract loader."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
TESTS_DIR = REPO_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from hermes_governance_fixtures import (  # noqa: E402
    governance_env,
    template_catalog_tool_names,
    template_governed_tool_names,
)


class TestGovernanceLoader(unittest.TestCase):
    def test_load_governed_tools(self) -> None:
        from hermes_governance import governed_tool_names, load_governed_tools, load_tool_catalog, supported_actions

        with governance_env():
            catalog = load_tool_catalog()
            tools = load_governed_tools()
            self.assertIn("terminal", catalog)
            self.assertIn("write_file", catalog)
            self.assertIn("terminal", tools)
            self.assertIn("write_file", tools)
            self.assertEqual(tools["write_file"].action, "WRITE_HOST_FILE")
            self.assertTrue(tools["terminal"].enabled)
            self.assertIn("terminal", governed_tool_names())
            self.assertIn("RUN_COMMAND", supported_actions())
            self.assertIn("DELETE_HOST_FILE", supported_actions())
            self.assertIn("HERMES_CRONJOB", supported_actions())
            self.assertEqual(frozenset(catalog), template_catalog_tool_names())
            self.assertEqual(frozenset(tools), template_governed_tool_names())

    def test_builtin_module_on_catalog_tools(self) -> None:
        from hermes_governance.loader import load_tool_catalog

        with governance_env():
            catalog = load_tool_catalog()
            self.assertEqual(catalog["terminal"].builtin_module, "tools.terminal_tool")
            self.assertEqual(catalog["process"].builtin_module, "tools.process_registry")
            self.assertEqual(catalog["write_file"].builtin_module, "tools.file_tools")
            self.assertEqual(catalog["patch"].builtin_module, "tools.file_tools")
            self.assertEqual(catalog["cronjob"].builtin_module, "tools.cronjob_tools")

    def test_invalid_builtin_module_prefix_raises(self) -> None:
        from hermes_governance.loader import load_tool_catalog

        yaml_text = """
tools:
  terminal:
    enabled: true
    action: RUN_COMMAND
    risk: local_process
    mapper: terminal
    builtin_module: os.path
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_text)
            path = handle.name

        try:
            load_tool_catalog.cache_clear()
            with self.assertRaises(ValueError):
                load_tool_catalog(path)
        finally:
            load_tool_catalog.cache_clear()
            Path(path).unlink(missing_ok=True)

    def test_generic_mapper_action_ids(self) -> None:
        from hermes_governance.loader import generic_mapper_action_ids

        with governance_env():
            self.assertEqual(generic_mapper_action_ids(), frozenset({"HERMES_CRONJOB"}))

    def test_enabled_false_excluded_from_governed_set(self) -> None:
        from hermes_governance.loader import load_governed_tools, load_tool_catalog

        yaml_text = """
tools:
  terminal:
    enabled: true
    action: RUN_COMMAND
    risk: local_process
    mapper: terminal
  write_file:
    enabled: false
    action: WRITE_HOST_FILE
    risk: local_write
    mapper: write_file
"""
        with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as handle:
            handle.write(yaml_text)
            path = handle.name

        try:
            load_tool_catalog.cache_clear()
            catalog = load_tool_catalog(path)
            governed = load_governed_tools(path)
            self.assertEqual(frozenset(catalog), frozenset({"terminal", "write_file"}))
            self.assertFalse(catalog["write_file"].enabled)
            self.assertEqual(frozenset(governed), frozenset({"terminal"}))
        finally:
            load_tool_catalog.cache_clear()
            Path(path).unlink(missing_ok=True)

    def test_invalid_hermes_governance_yaml_env_raises(self) -> None:
        from hermes_governance.loader import load_tool_catalog

        prev_env = os.environ.get("HERMES_GOVERNANCE_YAML")
        os.environ["HERMES_GOVERNANCE_YAML"] = "/nonexistent/hermes-governance-tools.yaml"
        load_tool_catalog.cache_clear()
        try:
            with self.assertRaises(FileNotFoundError):
                load_tool_catalog()
        finally:
            load_tool_catalog.cache_clear()
            if prev_env is None:
                os.environ.pop("HERMES_GOVERNANCE_YAML", None)
            else:
                os.environ["HERMES_GOVERNANCE_YAML"] = prev_env


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
