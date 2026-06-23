#!/usr/bin/env python3
"""Unit tests for governed builtin module preload."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _loader import load_plugin_module  # noqa: E402

preload_mod = load_plugin_module("builtin_preload")


def _spec(module: str | None) -> SimpleNamespace:
    return SimpleNamespace(builtin_module=module)


class PreloadGovernedBuiltinsTests(unittest.TestCase):
    def test_imports_unique_modules_from_governed_specs(self) -> None:
        governed_tools = {
            "terminal": _spec("tools.terminal_tool"),
            "write_file": _spec("tools.file_tools"),
            "patch": _spec("tools.file_tools"),
        }
        with mock.patch.object(preload_mod.importlib, "import_module") as import_module:
            preload_mod.preload_governed_builtins(governed_tools)

        import_module.assert_any_call("tools.terminal_tool")
        import_module.assert_any_call("tools.file_tools")
        self.assertEqual(import_module.call_count, 2)

    def test_imports_cronjob_module_when_governed(self) -> None:
        governed_tools = {"cronjob": _spec("tools.cronjob_tools")}
        with mock.patch.object(preload_mod.importlib, "import_module") as import_module:
            preload_mod.preload_governed_builtins(governed_tools)

        import_module.assert_called_once_with("tools.cronjob_tools")

    def test_skips_tools_without_builtin_module(self) -> None:
        governed_tools = {"unknown_future_tool": _spec(None)}
        with mock.patch.object(preload_mod.importlib, "import_module") as import_module:
            preload_mod.preload_governed_builtins(governed_tools)
        import_module.assert_not_called()


if __name__ == "__main__":
    unittest.main()
