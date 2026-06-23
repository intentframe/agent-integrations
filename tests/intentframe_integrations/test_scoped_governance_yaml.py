#!/usr/bin/env python3
"""Tests for scoped governance yaml generation and gateway E2E setup."""

from __future__ import annotations

import os
import shutil
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
GATEWAY_DIR = REPO_ROOT / "tests" / "hermes_gateway"
TESTS_DIR = REPO_ROOT / "tests"
SHARED_SRC = REPO_ROOT / "integrations" / "hermes" / "shared" / "src"

for path in (CLI_SRC, GATEWAY_DIR, TESTS_DIR, SHARED_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from intentframe_integrations.hermes_governance_contract import (  # noqa: E402
    write_scoped_governance_yaml,
)
from hermes_governance.loader import load_governed_tools, load_tool_catalog  # noqa: E402
from governance_e2e_setup import (  # noqa: E402
    assert_e2e_governance_snapshot,
    assert_governance_env_contract,
    cleanup_e2e_governance_yaml,
    format_gateway_probe_plan,
    format_governance_snapshot,
    load_e2e_governance_snapshot,
    log_e2e_governance,
    parse_governed_tools_env,
    setup_e2e_governance_yaml,
)
from hermes_governance_fixtures import template_catalog_tool_names  # noqa: E402


class TestWriteScopedGovernanceYaml(unittest.TestCase):
    def tearDown(self) -> None:
        load_tool_catalog.cache_clear()

    def test_all_governed_when_subset_unspecified(self) -> None:
        path = write_scoped_governance_yaml()
        try:
            catalog = load_tool_catalog(str(path))
            governed = load_governed_tools(str(path))
            self.assertEqual(set(catalog), set(governed))
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_only_listed_tools_governed(self) -> None:
        path = write_scoped_governance_yaml(governed_tools=frozenset({"terminal", "process"}))
        try:
            catalog = load_tool_catalog(str(path))
            governed = load_governed_tools(str(path))
            self.assertEqual(set(governed), {"terminal", "process"})
            self.assertFalse(catalog["write_file"].enabled)
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_unknown_tool_raises(self) -> None:
        with self.assertRaises(ValueError):
            write_scoped_governance_yaml(governed_tools=frozenset({"not_a_tool"}))


class TestGovernanceE2eSetup(unittest.TestCase):
    def tearDown(self) -> None:
        cleanup_e2e_governance_yaml()
        os.environ.pop("HERMES_GOVERNANCE_YAML", None)
        os.environ.pop("HERMES_E2E_GOVERNED_TOOLS", None)
        load_tool_catalog.cache_clear()

    def test_setup_all_governed_by_default(self) -> None:
        path = setup_e2e_governance_yaml()
        self.assertEqual(os.environ["HERMES_GOVERNANCE_YAML"], str(path))
        governed = load_governed_tools(str(path))
        self.assertIn("terminal", governed)
        self.assertIn("write_file", governed)

    def test_setup_scoped_governed_tools(self) -> None:
        os.environ["HERMES_E2E_GOVERNED_TOOLS"] = "terminal"
        path = setup_e2e_governance_yaml()
        governed = load_governed_tools(str(path))
        self.assertEqual(set(governed), {"terminal"})

    def test_respects_existing_hermes_governance_yaml(self) -> None:
        path = write_scoped_governance_yaml(governed_tools=frozenset({"process"}))
        try:
            os.environ["HERMES_GOVERNANCE_YAML"] = str(path)
            result = setup_e2e_governance_yaml()
            self.assertEqual(result, path)
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_parse_governed_tools_env(self) -> None:
        self.assertEqual(
            parse_governed_tools_env(" terminal , process "),
            frozenset({"terminal", "process"}),
        )

    def test_log_e2e_governance_reports_scoped_tools(self) -> None:
        governed = frozenset({"terminal", "process"})
        os.environ["HERMES_E2E_GOVERNED_TOOLS"] = "terminal,process"
        setup_e2e_governance_yaml()
        messages: list[str] = []

        snapshot = log_e2e_governance(log=messages.append)

        self.assertEqual(snapshot.governed, governed)
        self.assertEqual(snapshot.ungoverned, template_catalog_tool_names() - governed)
        joined = "\n".join(messages)
        self.assertIn("HERMES_E2E_GOVERNED_TOOLS", joined)
        self.assertIn("terminal: RUN", joined)
        self.assertIn("write_file: SKIP", joined)
        self.assertIn("cronjob: SKIP", joined)

    def test_assert_e2e_governance_snapshot_rejects_mismatch(self) -> None:
        path = write_scoped_governance_yaml(governed_tools=frozenset({"terminal"}))
        try:
            os.environ["HERMES_GOVERNANCE_YAML"] = str(path)
            os.environ["HERMES_E2E_GOVERNED_TOOLS"] = "process"
            snapshot = load_e2e_governance_snapshot()
            with self.assertRaises(AssertionError):
                assert_e2e_governance_snapshot(snapshot)
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_format_governance_snapshot_includes_ungoverned(self) -> None:
        path = write_scoped_governance_yaml(governed_tools=frozenset({"terminal"}))
        try:
            os.environ["HERMES_GOVERNANCE_YAML"] = str(path)
            text = format_governance_snapshot(load_e2e_governance_snapshot())
            self.assertIn("not governed", text)
            self.assertIn("process", text)
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)

    def test_format_gateway_probe_plan(self) -> None:
        text = format_gateway_probe_plan(frozenset({"terminal"}))
        self.assertIn("terminal: RUN", text)
        self.assertIn("process: SKIP", text)
        self.assertIn("cronjob: SKIP", text)

    def test_assert_governance_env_contract(self) -> None:
        os.environ["HERMES_E2E_GOVERNED_TOOLS"] = "terminal"
        setup_e2e_governance_yaml()
        snapshot = assert_governance_env_contract(label="test")
        self.assertEqual(snapshot.governed, frozenset({"terminal"}))


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
