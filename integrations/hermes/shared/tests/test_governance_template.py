#!/usr/bin/env python3
"""Governance default template contract in the repo."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[4]
TESTS_DIR = REPO_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from hermes_governance_fixtures import (  # noqa: E402
    PLUGIN_GOVERNANCE_COPY,
    default_governance_template_path,
)


class TestGovernanceTemplate(unittest.TestCase):
    def test_default_template_exists_and_has_tools(self) -> None:
        template = default_governance_template_path()
        self.assertTrue(template.is_file(), f"missing default template: {template}")
        raw = yaml.safe_load(template.read_text(encoding="utf-8"))
        tools = raw.get("tools")
        self.assertIsInstance(tools, dict)
        self.assertGreater(len(tools), 0)

    def test_no_duplicate_plugin_bundled_yaml(self) -> None:
        self.assertFalse(
            PLUGIN_GOVERNANCE_COPY.is_file(),
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
