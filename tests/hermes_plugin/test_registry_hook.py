#!/usr/bin/env python3
"""Registry hook lifecycle tests for intentframe-gate."""

from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from _loader import load_plugin_module  # noqa: E402
from governance_fixtures import PluginGovernanceEnvMixin  # noqa: E402

registry_hook_mod = load_plugin_module("registry_hook")
gate_mod = load_plugin_module("gate")


class RegistryEntry:
    def __init__(
        self,
        *,
        name: str,
        handler: Any,
        schema: dict[str, Any],
        is_async: bool = False,
    ) -> None:
        self.name = name
        self.toolset = "file"
        self.handler = handler
        self.schema = schema
        self.check_fn = None
        self.is_async = is_async
        self.emoji = ""


class FakeRegistry:
    def __init__(self) -> None:
        self.entries: dict[str, RegistryEntry] = {}
        self.register_calls = 0
        self.get_definitions_calls = 0

    def get_definitions(self, tool_names, *, quiet=False):
        del quiet
        self.get_definitions_calls += 1
        selected = tool_names if tool_names is not None else self.entries.keys()
        return [
            {
                "type": "function",
                "function": self.entries[name].schema,
            }
            for name in selected
            if name in self.entries
        ]

    def register(
        self,
        name: str,
        toolset: str,
        schema: dict,
        handler,
        check_fn=None,
        requires_env=None,
        is_async: bool = False,
        description: str = "",
        emoji: str = "",
        max_result_size_chars=None,
        dynamic_schema_overrides=None,
        override: bool = False,
    ):
        del toolset, check_fn, requires_env, description, emoji
        del max_result_size_chars, dynamic_schema_overrides
        self.register_calls += 1
        if override or name not in self.entries:
            self.entries[name] = RegistryEntry(
                name=name,
                handler=handler,
                schema=schema,
                is_async=is_async,
            )
        return self.entries[name]


class TestRegistryHook(PluginGovernanceEnvMixin, unittest.TestCase):
    def setUp(self) -> None:
        super().setUp()
        gate_mod.reset_session_client()

    def tearDown(self) -> None:
        gate_mod.reset_session_client()
        super().tearDown()

    def test_late_registration_is_gated(self) -> None:
        registry = FakeRegistry()

        def original(args: dict[str, Any], **kw: Any) -> str:
            return "original"

        registry_mod = types.ModuleType("tools.registry")
        registry_mod.registry = registry
        sys.modules["tools.registry"] = registry_mod

        registry_hook_mod.install_registry_hook()
        registry.register(
            "write_file",
            "file",
            {"parameters": {"type": "object", "properties": {"path": {"type": "string"}}}},
            original,
        )

        entry = registry.entries["write_file"]
        self.assertNotIn("reason", entry.schema["parameters"]["properties"])
        self.assertTrue(getattr(entry.handler, gate_mod.GATED_MARKER, False))

    def test_refresh_reregistration_stays_gated(self) -> None:
        registry = FakeRegistry()

        def original(args: dict[str, Any], **kw: Any) -> str:
            return "original"

        def refreshed(args: dict[str, Any], **kw: Any) -> str:
            return "refreshed"

        registry_mod = types.ModuleType("tools.registry")
        registry_mod.registry = registry
        sys.modules["tools.registry"] = registry_mod

        registry_hook_mod.install_registry_hook()
        schema = {"parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}
        registry.register("write_file", "file", schema, original)
        registry.register("write_file", "file", schema, refreshed, override=True)

        entry = registry.entries["write_file"]
        self.assertNotIn("reason", entry.schema["parameters"]["properties"])
        self.assertTrue(getattr(entry.handler, gate_mod.GATED_MARKER, False))
        self.assertNotEqual(entry.handler, original)
        self.assertNotEqual(entry.handler, refreshed)

    def test_install_registry_hook_does_not_import_model_tools(self) -> None:
        registry = FakeRegistry()
        registry_mod = types.ModuleType("tools.registry")
        registry_mod.registry = registry
        sys.modules["tools.registry"] = registry_mod

        self.assertNotIn("model_tools", sys.modules)
        registry_hook_mod.install_registry_hook()
        self.assertNotIn("model_tools", sys.modules)

    def test_get_definitions_injects_reason_for_governed_tools(self) -> None:
        registry = FakeRegistry()
        registry.entries["write_file"] = RegistryEntry(
            name="write_file",
            handler=lambda args, **kw: "ok",
            schema={
                "name": "write_file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        )
        registry.entries["vision_analyze"] = RegistryEntry(
            name="vision_analyze",
            handler=lambda args, **kw: "ok",
            schema={
                "name": "vision_analyze",
                "parameters": {
                    "type": "object",
                    "properties": {"image": {"type": "string"}},
                    "required": ["image"],
                },
            },
        )

        registry_mod = types.ModuleType("tools.registry")
        registry_mod.registry = registry
        sys.modules["tools.registry"] = registry_mod

        registry_hook_mod.install_registry_hook()
        tool_defs = registry.get_definitions({"write_file", "vision_analyze"})
        by_name = {td["function"]["name"]: td["function"] for td in tool_defs}

        write_fn = by_name["write_file"]
        self.assertIn("reason", write_fn["parameters"]["properties"])
        self.assertIn("reason", write_fn["parameters"]["required"])

        vision_fn = by_name["vision_analyze"]
        self.assertNotIn("reason", vision_fn["parameters"]["properties"])


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
