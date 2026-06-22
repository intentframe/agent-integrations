#!/usr/bin/env python3
"""Tests for runtime-only governance config seeding."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
TESTS_DIR = REPO_ROOT / "tests"

for path in (CLI_SRC, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hermes_governance_fixtures import copy_default_template  # noqa: E402

from intentframe_integrations.hermes_governance_contract import (  # noqa: E402
    ensure_runtime_governance_yaml,
    governance_yaml_runtime_path,
    reset_runtime_governance_yaml,
)


class TestGovernanceRuntimeContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.runtime = self.root / "runtime" / "tools.yaml"
        self.runtime.parent.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_seed_does_not_overwrite_existing_runtime(self) -> None:
        copy_default_template(self.runtime)
        self.runtime.write_text("tools: {}\n", encoding="utf-8")

        with patch(
            "intentframe_integrations.hermes_governance_contract.governance_yaml_runtime_path",
            return_value=self.runtime,
        ):
            path = ensure_runtime_governance_yaml("hermes")

        self.assertEqual(path, self.runtime)
        self.assertEqual(self.runtime.read_text(encoding="utf-8"), "tools: {}\n")

    def test_reset_overwrites_runtime(self) -> None:
        self.runtime.write_text("tools: {}\n", encoding="utf-8")

        with patch(
            "intentframe_integrations.hermes_governance_contract.governance_yaml_runtime_path",
            return_value=self.runtime,
        ):
            path = reset_runtime_governance_yaml("hermes")

        self.assertEqual(path, self.runtime)
        self.assertIn("terminal", self.runtime.read_text(encoding="utf-8"))

    def test_runtime_path_is_under_intentframe(self) -> None:
        path = governance_yaml_runtime_path("hermes")
        self.assertIn(".intentframe", str(path))
        self.assertTrue(str(path).endswith("governance/tools.yaml"))


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
