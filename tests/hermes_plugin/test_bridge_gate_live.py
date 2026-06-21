#!/usr/bin/env python3
"""Live integration: Hermes plugin gate via adapter sidecar."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _loader import load_plugin_module  # noqa: E402

gate_mod = load_plugin_module("gate")


class TestLiveBridgeGate(unittest.TestCase):
    def setUp(self) -> None:
        gate_mod.reset_session_client()

    def tearDown(self) -> None:
        gate_mod.reset_session_client()

    def test_allow_benign_command(self) -> None:
        delegate = MagicMock(return_value='{"exit_code": 0, "status": "ok"}')
        out = gate_mod.gate_terminal_call(
            {"command": "echo hermes-plugin-bridge-ok", "reason": "Live bridge allow test"},
            delegate=delegate,
        )
        body = json.loads(out)
        self.assertEqual(body.get("exit_code"), 0)
        delegate.assert_called_once()

    def test_block_dangerous_command(self) -> None:
        delegate = MagicMock()
        out = gate_mod.gate_terminal_call(
            {"command": "sudo rm -rf /", "reason": "Should be blocked by policy"},
            delegate=delegate,
        )
        body = json.loads(out)
        self.assertEqual(body["exit_code"], -1)
        self.assertEqual(body["status"], "blocked")
        delegate.assert_not_called()


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
