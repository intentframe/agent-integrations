#!/usr/bin/env python3
"""Tests for catalog-all-governed governance yaml generator."""

from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "tests" / "scripts"
SHARED_SRC = REPO_ROOT / "integrations" / "hermes" / "shared" / "src"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(SHARED_SRC) not in sys.path:
    sys.path.insert(0, str(SHARED_SRC))

import make_catalog_yaml  # noqa: E402
from hermes_governance.loader import load_governed_tools, load_tool_catalog  # noqa: E402


class TestMakeCatalogYaml(unittest.TestCase):
    def tearDown(self) -> None:
        load_tool_catalog.cache_clear()

    def test_all_catalog_tools_governed_in_output(self) -> None:
        path = make_catalog_yaml.write_catalog_all_governed_yaml()
        try:
            catalog = load_tool_catalog(str(path))
            governed = load_governed_tools(str(path))
            self.assertEqual(set(catalog), set(governed))
            self.assertTrue(all(spec.enabled for spec in catalog.values()))
        finally:
            shutil.rmtree(path.parent, ignore_errors=True)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
