#!/usr/bin/env python3
"""Ensure canonical and plugin-bundled governance YAML stay in sync."""

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


class TestGovernanceSync(unittest.TestCase):
    def test_plugin_copy_matches_canonical(self) -> None:
        canonical = yaml.safe_load(CANONICAL.read_text(encoding="utf-8"))
        plugin_copy = yaml.safe_load(PLUGIN_COPY.read_text(encoding="utf-8"))
        self.assertEqual(canonical, plugin_copy)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
