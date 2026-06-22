#!/usr/bin/env python3
"""Unit tests for hermes-governance contract loader."""

from __future__ import annotations

import sys
import unittest


class TestGovernanceLoader(unittest.TestCase):
    def test_load_governed_tools(self) -> None:
        from hermes_governance import governed_tool_names, load_governed_tools, supported_actions

        tools = load_governed_tools()
        self.assertIn("terminal", tools)
        self.assertIn("write_file", tools)
        self.assertEqual(tools["write_file"].action, "WRITE_HOST_FILE")
        self.assertIn("terminal", governed_tool_names())
        self.assertIn("RUN_COMMAND", supported_actions())
        self.assertIn("DELETE_HOST_FILE", supported_actions())


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
