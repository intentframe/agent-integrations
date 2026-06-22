#!/usr/bin/env python3
"""Governance contract: single canonical YAML in the repo."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
CANONICAL = REPO_ROOT / "integrations" / "hermes" / "governance" / "tools.yaml"
PLUGIN_COPY = (
    REPO_ROOT
    / "integrations"
    / "hermes"
    / "plugin"
    / "intentframe-gate"
    / "governance"
    / "tools.yaml"
)


class TestGovernanceContract(unittest.TestCase):
    def test_canonical_yaml_exists_and_has_tools(self) -> None:
        self.assertTrue(CANONICAL.is_file(), f"missing canonical contract: {CANONICAL}")
        raw = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
        tools = raw.get("tools")
        self.assertIsInstance(tools, dict)
        self.assertGreater(len(tools), 0)

    def test_no_duplicate_plugin_bundled_yaml(self) -> None:
        self.assertFalse(
            PLUGIN_COPY.is_file(),
            "plugin/intentframe-gate/governance/tools.yaml must not exist; "
            "use integrations/hermes/governance/tools.yaml only",
        )


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
