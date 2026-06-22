#!/usr/bin/env python3
"""Unit tests for intentframe-gate plugin (adapter client injected)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
_REPO_TESTS = TESTS_DIR.parent
for path in (TESTS_DIR, _REPO_TESTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from _loader import load_plugin_module  # noqa: E402
from governance_fixtures import PluginGovernanceEnvMixin  # noqa: E402
from hermes_governance_fixtures import ensure_shared_loader_importable  # noqa: E402

schema_mod = load_plugin_module("schema")
gate_mod = load_plugin_module("gate")
governance_mod = load_plugin_module("governance_loader")


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
    def test_inject_reason_adds_required_field(self) -> None:
        built = schema_mod.inject_reason(
            {
                "name": "write_file",
                "description": "Write a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
            tool_name="write_file",
        )
        required = built["parameters"]["required"]
        self.assertIn("path", required)
        self.assertIn("reason", required)
        self.assertIn("reason", built["parameters"]["properties"])

    def test_inject_reason_idempotent(self) -> None:
        schema = {
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            }
        }
        once = schema_mod.inject_reason(schema, tool_name="terminal")
        twice = schema_mod.inject_reason(once, tool_name="terminal")
        self.assertEqual(
            twice["parameters"]["required"].count("reason"),
            1,
        )


class TestPluginGovernance(PluginGovernanceEnvMixin, unittest.TestCase):
    def test_plugin_loader_matches_shared_template(self) -> None:
        ensure_shared_loader_importable()
        from hermes_governance.loader import load_governed_tools as shared_load_governed

        plugin_names = frozenset(governance_mod.load_governed_tools().keys())
        shared_names = frozenset(shared_load_governed().keys())
        self.assertEqual(plugin_names, shared_names)


class TestGateToolCall(PluginGovernanceEnvMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        gate_mod.reset_session_client()

    def tearDown(self) -> None:
        gate_mod.reset_session_client()
        super().tearDown()

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

            def __call__(self, args: dict[str, Any], **kwargs: Any) -> str:
                Delegate.called = True
                return "{}"

        delegate = Delegate()
        out = gate_mod.gate_tool_call(
            "terminal",
            {"command": "sudo x", "reason": "Should block"},
            delegate=delegate,
            validator=validator,
        )
        body = json.loads(out)
        self.assertEqual(body["status"], "blocked")
        self.assertFalse(delegate.called)

    def test_allows_and_strips_reason(self) -> None:
        validator = FakeValidator({"allowed": True})

        def delegate(args: dict[str, Any], **kwargs: Any) -> str:
            self.assertNotIn("reason", args)
            return '{"status": "ok"}'

        out = gate_mod.gate_tool_call(
            "write_file",
            {"path": "~/x.txt", "content": "hi", "reason": "Save file"},
            delegate=delegate,
            validator=validator,
        )
        self.assertEqual(out, '{"status": "ok"}')
        self.assertEqual(validator.calls[0][0], "write_file")

    def test_generic_blocked_response(self) -> None:
        validator = FakeValidator(
            {
                "allowed": False,
                "error": "blocked",
                "agent_response": {"status": "blocked", "error": "blocked"},
            }
        )

        class Delegate:
            def __call__(self, args: dict[str, Any], **kwargs: Any) -> str:
                return "{}"

        out = gate_mod.gate_tool_call(
            "write_file",
            {"path": "~/x", "content": "y", "reason": "Test"},
            delegate=Delegate(),
            validator=validator,
        )
        body = json.loads(out)
        self.assertEqual(body["status"], "blocked")
        self.assertNotIn("exit_code", body)

    def test_wrap_handler_marks_gated(self) -> None:
        def original(args: dict[str, Any], **kw: Any) -> str:
            return "ok"

        wrapped = gate_mod.wrap_handler("terminal", original, is_async=False)
        self.assertTrue(getattr(wrapped, gate_mod.GATED_MARKER, False))
        wrapped_again = gate_mod.wrap_handler("terminal", wrapped, is_async=False)
        self.assertIs(wrapped, wrapped_again)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
