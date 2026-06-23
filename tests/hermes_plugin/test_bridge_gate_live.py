#!/usr/bin/env python3
"""Live integration: Hermes plugin gate via adapter sidecar."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

TESTS_DIR = Path(__file__).resolve().parent
ADAPTER_TESTS = TESTS_DIR.parent / "hermes_adapter"
for path in (TESTS_DIR, ADAPTER_TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from _loader import load_plugin_module  # noqa: E402
from live_fixtures import (  # noqa: E402
    CRONJOB_SEMANTIC_ARGS,
    PATCH_ALLOW_REPLACE_ARGS,
    PATCH_BLOCK_REPLACE_ARGS,
    PATCH_V4A_BLOCK_ARGS,
    PATCH_V4A_MIXED_HOME_DELETE_ARGS,
    PROCESS_ALLOW_ARGS,
    PROCESS_BLOCK_ARGS,
    WRITE_ALLOW_ARGS,
    WRITE_BLOCK_ARGS,
)

gate_mod = load_plugin_module("gate")


class TestLiveBridgeGate(unittest.TestCase):
    def setUp(self) -> None:
        gate_mod.reset_session_client()

    def tearDown(self) -> None:
        gate_mod.reset_session_client()

    def _assert_allowed(self, tool: str, args: dict[str, object], *, delegate: MagicMock) -> None:
        out = gate_mod.gate_tool_call(tool, args, delegate=delegate)
        body = json.loads(out)
        self.assertEqual(body.get("status"), "ok")
        delegate.assert_called_once()
        forwarded = delegate.call_args.args[0]
        self.assertNotIn("reason", forwarded)

    def _assert_blocked(self, tool: str, args: dict[str, object], *, delegate: MagicMock) -> None:
        out = gate_mod.gate_tool_call(tool, args, delegate=delegate)
        body = json.loads(out)
        self.assertEqual(body["status"], "blocked")
        delegate.assert_not_called()

    def _assert_semantic_gate(self, tool: str, args: dict[str, object], *, delegate: MagicMock) -> None:
        out = gate_mod.gate_tool_call(tool, args, delegate=delegate)
        body = json.loads(out)
        status = body.get("status")
        if status == "ok":
            delegate.assert_called_once()
            return
        if status == "blocked":
            delegate.assert_not_called()
            self.assertTrue(body.get("error") or body.get("agent_response"))
            return
        self.fail(f"Unexpected semantic gate response: {body!r}")

    def test_allow_terminal(self) -> None:
        delegate = MagicMock(return_value='{"exit_code": 0, "status": "ok"}')
        out = gate_mod.gate_tool_call(
            "terminal",
            {"command": "echo hermes-plugin-bridge-ok", "reason": "Live bridge allow test"},
            delegate=delegate,
        )
        body = json.loads(out)
        self.assertEqual(body.get("exit_code"), 0)
        delegate.assert_called_once()

    def test_block_terminal(self) -> None:
        delegate = MagicMock()
        out = gate_mod.gate_tool_call(
            "terminal",
            {"command": "sudo rm -rf /", "reason": "Should be blocked by policy"},
            delegate=delegate,
        )
        body = json.loads(out)
        self.assertEqual(body["exit_code"], -1)
        self.assertEqual(body["status"], "blocked")
        delegate.assert_not_called()

    def test_allow_process(self) -> None:
        delegate = MagicMock(return_value='{"status": "ok"}')
        self._assert_allowed("process", PROCESS_ALLOW_ARGS, delegate=delegate)

    def test_block_process(self) -> None:
        delegate = MagicMock()
        self._assert_blocked("process", PROCESS_BLOCK_ARGS, delegate=delegate)

    def test_allow_write_file(self) -> None:
        delegate = MagicMock(return_value='{"status": "ok"}')
        self._assert_allowed("write_file", WRITE_ALLOW_ARGS, delegate=delegate)

    def test_block_write_file(self) -> None:
        delegate = MagicMock()
        self._assert_blocked("write_file", WRITE_BLOCK_ARGS, delegate=delegate)

    def test_patch_replace_allow_semantic(self) -> None:
        delegate = MagicMock(return_value='{"status": "ok"}')
        self._assert_semantic_gate("patch", PATCH_ALLOW_REPLACE_ARGS, delegate=delegate)

    def test_block_patch_replace(self) -> None:
        delegate = MagicMock()
        self._assert_blocked("patch", PATCH_BLOCK_REPLACE_ARGS, delegate=delegate)

    def test_patch_v4a_mixed_home_delete_semantic(self) -> None:
        delegate = MagicMock(return_value='{"status": "ok"}')
        self._assert_semantic_gate("patch", PATCH_V4A_MIXED_HOME_DELETE_ARGS, delegate=delegate)

    def test_block_patch_v4a_mixed_system_delete(self) -> None:
        delegate = MagicMock()
        self._assert_blocked("patch", PATCH_V4A_BLOCK_ARGS, delegate=delegate)

    def test_cronjob_semantic(self) -> None:
        delegate = MagicMock(return_value='{"status": "ok"}')
        self._assert_semantic_gate("cronjob", CRONJOB_SEMANTIC_ARGS, delegate=delegate)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
