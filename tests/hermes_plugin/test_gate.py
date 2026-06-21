#!/usr/bin/env python3
"""Unit tests for intentframe-terminal plugin gate (adapter client injected)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _loader import load_plugin_module  # noqa: E402

schema_mod = load_plugin_module("schema")
gate_mod = load_plugin_module("gate")


class FakeValidator:
    def __init__(self, response: dict[str, Any]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any] | None]] = []

    def validate_tool(
        self,
        tool: str,
        args: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((tool, args, context))
        return self.response


class TestSchema(unittest.TestCase):
    def test_fallback_schema_requires_reason(self) -> None:
        built = schema_mod.build_terminal_schema()
        required = built["parameters"]["required"]
        self.assertIn("command", required)
        self.assertIn("reason", required)


class TestGateTerminalCall(unittest.TestCase):
    def setUp(self) -> None:
        gate_mod.reset_session_client()

    def tearDown(self) -> None:
        gate_mod.reset_session_client()

    def test_blocks_via_adapter(self) -> None:
        validator = FakeValidator(
            {
                "allowed": False,
                "agent_response": {
                    "exit_code": -1,
                    "status": "blocked",
                    "error": "policy",
                },
            }
        )

        class Delegate:
            called = False

            def __call__(self, **kwargs: Any) -> str:
                Delegate.called = True
                return "{}"

        delegate = Delegate()
        out = gate_mod.gate_terminal_call(
            {"command": "sudo x", "reason": "Should block"},
            delegate=delegate,
            validator=validator,
        )
        body = json.loads(out)
        self.assertEqual(body["status"], "blocked")
        self.assertFalse(delegate.called)

    def test_allows_and_strips_reason(self) -> None:
        validator = FakeValidator({"allowed": True})

        def delegate(**kwargs: Any) -> str:
            self.assertNotIn("reason", kwargs)
            return '{"exit_code": 0}'

        out = gate_mod.gate_terminal_call(
            {"command": "echo ok", "reason": "Smoke test", "background": True},
            delegate=delegate,
            validator=validator,
        )
        self.assertEqual(out, '{"exit_code": 0}')
        self.assertEqual(validator.calls[0][0], "terminal")

    def test_infrastructure_error_status(self) -> None:
        validator = FakeValidator(
            {
                "allowed": False,
                "error": "Adapter socket missing",
                "agent_response": {
                    "exit_code": -1,
                    "status": "error",
                    "error": "Adapter socket missing",
                },
            }
        )

        class Delegate:
            called = False

            def __call__(self, **kwargs: Any) -> str:
                Delegate.called = True
                return "{}"

        out = gate_mod.gate_terminal_call(
            {"command": "echo ok", "reason": "Should fail closed"},
            delegate=Delegate(),
            validator=validator,
        )
        body = json.loads(out)
        self.assertEqual(body["status"], "error")


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
