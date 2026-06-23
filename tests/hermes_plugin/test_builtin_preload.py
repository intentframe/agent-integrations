#!/usr/bin/env python3
"""Unit tests for governed builtin module preload."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _loader import load_plugin_module  # noqa: E402

preload_mod = load_plugin_module("builtin_preload")


class PreloadGovernedBuiltinsTests(unittest.TestCase):
    def test_imports_unique_modules_for_governed_tools(self) -> None:
        governed = frozenset({"terminal", "write_file", "patch"})
        with mock.patch.object(preload_mod.importlib, "import_module") as import_module:
            preload_mod.preload_governed_builtins(governed)

        import_module.assert_any_call("tools.terminal_tool")
        import_module.assert_any_call("tools.file_tools")
        self.assertEqual(import_module.call_count, 2)

    def test_skips_unknown_governed_tools(self) -> None:
        governed = frozenset({"unknown_future_tool"})
        with mock.patch.object(preload_mod.importlib, "import_module") as import_module:
            preload_mod.preload_governed_builtins(governed)
        import_module.assert_not_called()


if __name__ == "__main__":
    unittest.main()
