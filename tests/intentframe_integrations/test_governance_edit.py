#!/usr/bin/env python3
"""Tests for governance enable/disable editing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
SHARED_SRC = REPO_ROOT / "integrations" / "hermes" / "shared" / "src"
TESTS_DIR = REPO_ROOT / "tests"

for path in (CLI_SRC, SHARED_SRC, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hermes_governance_fixtures import copy_default_template  # noqa: E402

from intentframe_integrations.hermes_governance_edit import (  # noqa: E402
    GovernanceEditError,
    list_governed_tools,
    set_tool_enabled,
)
from hermes_governance.loader import load_governed_tools, load_tool_catalog  # noqa: E402


class TestGovernanceEdit(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.yaml_path = Path(self.temp_dir.name) / "tools.yaml"
        copy_default_template(self.yaml_path)

    def tearDown(self) -> None:
        load_tool_catalog.cache_clear()
        self.temp_dir.cleanup()

    def test_disable_then_load_excludes_tool(self) -> None:
        set_tool_enabled("write_file", False, yaml_path=self.yaml_path)
        catalog = load_tool_catalog(str(self.yaml_path))
        governed = load_governed_tools(str(self.yaml_path))
        self.assertIn("write_file", catalog)
        self.assertFalse(catalog["write_file"].enabled)
        self.assertNotIn("write_file", governed)

    def test_enable_restores_tool(self) -> None:
        set_tool_enabled("write_file", False, yaml_path=self.yaml_path)
        set_tool_enabled("write_file", True, yaml_path=self.yaml_path)
        governed = load_governed_tools(str(self.yaml_path))
        self.assertIn("write_file", governed)

    def test_disable_last_enabled_tool_raises(self) -> None:
        entries = list_governed_tools(yaml_path=self.yaml_path)
        for name, _enabled in entries:
            if name == "terminal":
                continue
            set_tool_enabled(name, False, yaml_path=self.yaml_path)

        with self.assertRaises(GovernanceEditError):
            set_tool_enabled("terminal", False, yaml_path=self.yaml_path)

    def test_unknown_tool_raises(self) -> None:
        with self.assertRaises(GovernanceEditError):
            set_tool_enabled("not_a_tool", False, yaml_path=self.yaml_path)

    def test_enabled_field_persisted_in_yaml(self) -> None:
        set_tool_enabled("write_file", False, yaml_path=self.yaml_path)
        raw = yaml.safe_load(self.yaml_path.read_text(encoding="utf-8"))
        self.assertFalse(raw["tools"]["write_file"]["enabled"])

    def test_idempotent_disable(self) -> None:
        path1 = set_tool_enabled("write_file", False, yaml_path=self.yaml_path)
        path2 = set_tool_enabled("write_file", False, yaml_path=self.yaml_path)
        self.assertEqual(path1, path2)


class TestGovernanceCli(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.yaml_path = Path(self.temp_dir.name) / "tools.yaml"
        copy_default_template(self.yaml_path)
        load_tool_catalog.cache_clear()

    def tearDown(self) -> None:
        load_tool_catalog.cache_clear()
        self.temp_dir.cleanup()

    def test_cli_disable_updates_yaml(self) -> None:
        from unittest.mock import patch

        from intentframe_integrations.cli import main

        with patch(
            "intentframe_integrations.hermes_governance_edit.active_governance_yaml_path",
            return_value=self.yaml_path,
        ):
            ec = main(["governance", "disable", "hermes", "write_file"])
        self.assertEqual(ec, 0)
        raw = yaml.safe_load(self.yaml_path.read_text(encoding="utf-8"))
        self.assertFalse(raw["tools"]["write_file"]["enabled"])

    def test_cli_disable_last_tool_fails(self) -> None:
        from unittest.mock import patch

        from intentframe_integrations.cli import main

        for name, _enabled in list_governed_tools(yaml_path=self.yaml_path):
            if name == "terminal":
                continue
            set_tool_enabled(name, False, yaml_path=self.yaml_path)

        with patch(
            "intentframe_integrations.hermes_governance_edit.active_governance_yaml_path",
            return_value=self.yaml_path,
        ):
            ec = main(["governance", "disable", "hermes", "terminal"])
        self.assertEqual(ec, 1)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
