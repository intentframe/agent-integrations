#!/usr/bin/env python3
"""Unit tests for hermes-adapter mapper and service."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
TESTS_DIR = REPO_ROOT / "tests"
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from hermes_governance_fixtures import (  # noqa: E402
    install_test_governance_env,
    restore_test_governance_env,
)


def setUpModule() -> None:
    install_test_governance_env()


def tearDownModule() -> None:
    restore_test_governance_env()


class FakeBridge:
    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        self.requests: list[dict[str, Any]] = []

    def validate(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        return self.result

    def close(self) -> None:
        return None


class TestMapper(unittest.TestCase):
    def test_map_terminal(self) -> None:
        from hermes_adapter.mapper import map_terminal

        intents = map_terminal({"command": "echo hi", "reason": "List files"})
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["action"], "RUN_COMMAND")
        self.assertEqual(intents[0]["command"], "echo hi")
        self.assertEqual(intents[0]["reason"], "List files")

    def test_map_process(self) -> None:
        from hermes_adapter.mapper import map_process

        intents = map_process(
            {"action": "kill", "session_id": "abc", "reason": "Stop runaway"}
        )
        self.assertEqual(intents[0]["action"], "RUN_COMMAND")
        self.assertIn("process:kill", intents[0]["command"])

    def test_map_write_file(self) -> None:
        from hermes_adapter.mapper import map_write_file

        intents = map_write_file(
            {"path": "~/notes.txt", "content": "hello", "reason": "Save notes"}
        )
        self.assertEqual(intents[0]["action"], "WRITE_HOST_FILE")
        self.assertEqual(intents[0]["path"], "~/notes.txt")
        self.assertEqual(intents[0]["content"], "hello")

    def test_map_delete_file(self) -> None:
        from hermes_adapter.mapper import map_delete_file

        intents = map_delete_file({"path": "~/notes.txt", "reason": "Remove notes"})
        self.assertEqual(intents[0]["action"], "DELETE_HOST_FILE")
        self.assertEqual(intents[0]["path"], "~/notes.txt")
        self.assertNotIn("content", intents[0])
        self.assertTrue(intents[0]["irreversible"])

    def test_map_patch_replace(self) -> None:
        from hermes_adapter.mapper import map_patch

        intents = map_patch(
            {
                "mode": "replace",
                "path": "~/x.py",
                "old_string": "a",
                "new_string": "b",
                "reason": "Fix typo",
            }
        )
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["action"], "WRITE_HOST_FILE")
        self.assertEqual(intents[0]["path"], "~/x.py")
        self.assertNotIn("patch_op_index", intents[0])
        self.assertNotIn("patch_operations", intents[0])

    def test_map_patch_v4a_multi_file(self) -> None:
        from hermes_adapter.mapper import map_patch

        patch = (
            "*** Begin Patch\n"
            "*** Update File: ~/a.py\n"
            "@@\n"
            "-old\n"
            "+new\n"
            "*** Update File: ~/b.py\n"
            "@@\n"
            "-x\n"
            "+y\n"
            "*** End Patch"
        )
        intents = map_patch({"mode": "patch", "patch": patch, "reason": "Bulk edit"})
        self.assertEqual(len(intents), 2)
        paths = {intent["path"] for intent in intents}
        self.assertEqual(paths, {"~/a.py", "~/b.py"})
        self.assertEqual(intents[0]["reason"], "Bulk edit [patch op 1/2: update ~/a.py]")
        self.assertEqual(intents[1]["reason"], "Bulk edit [patch op 2/2: update ~/b.py]")
        self.assertEqual(intents[0]["patch_op_index"], 1)
        self.assertEqual(intents[0]["patch_op_count"], 2)
        self.assertEqual(
            intents[0]["patch_operations"],
            [{"kind": "update", "path": "~/a.py"}, {"kind": "update", "path": "~/b.py"}],
        )
        self.assertIn("~/a.py", intents[0]["content"])
        self.assertNotIn("~/b.py", intents[0]["content"])
        self.assertIn("~/b.py", intents[1]["content"])
        self.assertNotIn("~/a.py", intents[1]["content"])
        self.assertIsNot(intents[0]["patch_operations"], intents[1]["patch_operations"])

    def test_map_patch_v4a_scoped_content_excludes_siblings(self) -> None:
        from hermes_adapter.mapper import map_patch

        patch = (
            "*** Begin Patch\n"
            "*** Update File: ~/keep.py\n"
            "@@\n"
            "-old\n"
            "+new\n"
            "*** Delete File: /etc/system-probe\n"
            "*** End Patch"
        )
        intents = map_patch({"mode": "patch", "patch": patch, "reason": "Mixed patch"})
        write_intent = intents[0]
        delete_intent = intents[1]
        self.assertEqual(write_intent["action"], "WRITE_HOST_FILE")
        self.assertEqual(delete_intent["action"], "DELETE_HOST_FILE")
        self.assertIn("~/keep.py", write_intent["content"])
        self.assertNotIn("/etc/system-probe", write_intent["content"])
        self.assertEqual(delete_intent["reason"], "Mixed patch [patch op 2/2: delete /etc/system-probe]")

    def test_map_patch_v4a_delete(self) -> None:
        from hermes_adapter.mapper import map_patch

        patch = (
            "*** Begin Patch\n"
            "*** Delete File: ~/old.txt\n"
            "*** End Patch"
        )
        intents = map_patch({"mode": "patch", "patch": patch, "reason": "Remove file"})
        self.assertEqual(len(intents), 1)
        self.assertEqual(intents[0]["action"], "DELETE_HOST_FILE")
        self.assertEqual(intents[0]["path"], "~/old.txt")
        self.assertTrue(intents[0]["irreversible"])
        self.assertEqual(intents[0]["reason"], "Remove file [patch op 1/1: delete ~/old.txt]")
        self.assertEqual(intents[0]["patch_op_count"], 1)

    def test_map_patch_v4a_mixed_write_delete(self) -> None:
        from hermes_adapter.mapper import map_patch

        patch = (
            "*** Begin Patch\n"
            "*** Update File: ~/keep.py\n"
            "@@\n"
            "-old\n"
            "+new\n"
            "*** Delete File: ~/drop.py\n"
            "*** End Patch"
        )
        intents = map_patch({"mode": "patch", "patch": patch, "reason": "Mixed edit"})
        self.assertEqual(len(intents), 2)
        self.assertEqual(intents[0]["action"], "WRITE_HOST_FILE")
        self.assertEqual(intents[1]["action"], "DELETE_HOST_FILE")
        self.assertNotIn("~/drop.py", intents[0]["content"])
        self.assertEqual(intents[0]["reason"], "Mixed edit [patch op 1/2: update ~/keep.py]")
        self.assertEqual(intents[1]["reason"], "Mixed edit [patch op 2/2: delete ~/drop.py]")

    def test_missing_reason(self) -> None:
        from hermes_adapter.mapper import ValidationError, map_terminal

        with self.assertRaises(ValidationError):
            map_terminal({"command": "echo hi"})

    def test_supported_tools(self) -> None:
        from hermes_adapter.mapper import supported_tools

        tools = supported_tools()
        self.assertIn("terminal", tools)
        self.assertIn("write_file", tools)
        self.assertIn("delete_file", tools)
        self.assertEqual(tools["write_file"], "WRITE_HOST_FILE")
        self.assertEqual(tools["delete_file"], "DELETE_HOST_FILE")

    def test_unknown_tool(self) -> None:
        from hermes_adapter.mapper import ValidationError, map_tool

        with self.assertRaises(ValidationError):
            map_tool("read_file", {"reason": "noop"})


class TestValidateService(unittest.TestCase):
    def test_allow(self) -> None:
        from hermes_adapter.service import ValidateService

        bridge = FakeBridge({"allowed": True, "success": True, "validated_only": True})
        service = ValidateService(bridge=bridge)  # type: ignore[arg-type]
        out = service.validate_tool("terminal", {"command": "echo ok", "reason": "Smoke test"})
        self.assertTrue(out["allowed"])
        self.assertEqual(len(bridge.requests), 1)

    def test_block(self) -> None:
        from hermes_adapter.service import ValidateService

        bridge = FakeBridge({"allowed": False, "error": "blocked by policy"})
        service = ValidateService(bridge=bridge)  # type: ignore[arg-type]
        out = service.validate_tool("terminal", {"command": "sudo x", "reason": "Should block"})
        self.assertFalse(out["allowed"])
        self.assertIn("agent_response", out)
        self.assertEqual(out["agent_response"]["status"], "blocked")
        self.assertEqual(out["agent_response"]["exit_code"], -1)

    def test_block_write_file_uses_generic_json(self) -> None:
        from hermes_adapter.service import ValidateService

        bridge = FakeBridge({"allowed": False, "error": "blocked by policy"})
        service = ValidateService(bridge=bridge)  # type: ignore[arg-type]
        out = service.validate_tool(
            "write_file",
            {"path": "/etc/x", "content": "y", "reason": "Should block"},
        )
        self.assertFalse(out["allowed"])
        agent_response = out["agent_response"]
        self.assertEqual(agent_response["status"], "blocked")
        self.assertNotIn("exit_code", agent_response)

    def test_block_terminal_preflight_uses_terminal_json(self) -> None:
        from hermes_adapter.service import ValidateService

        service = ValidateService(bridge=FakeBridge({"allowed": True}))  # type: ignore[arg-type]
        out = service.validate_tool("terminal", {"command": "echo hi"})
        self.assertFalse(out["allowed"])
        self.assertEqual(out["agent_response"]["exit_code"], -1)
        self.assertEqual(out["agent_response"]["status"], "blocked")

    def test_multi_intent_blocks_on_second(self) -> None:
        from hermes_adapter.service import ValidateService

        class TwoStepBridge:
            def __init__(self) -> None:
                self.requests: list[dict[str, Any]] = []
                self._count = 0

            def validate(self, request: dict[str, Any]) -> dict[str, Any]:
                self.requests.append(request)
                self._count += 1
                if self._count == 1:
                    return {"allowed": True}
                return {"allowed": False, "error": "blocked path"}

            def close(self) -> None:
                return None

        patch = (
            "*** Begin Patch\n"
            "*** Update File: ~/ok.py\n"
            "*** Update File: /etc/bad\n"
            "*** End Patch"
        )
        bridge = TwoStepBridge()
        service = ValidateService(bridge=bridge)  # type: ignore[arg-type]
        out = service.validate_tool("patch", {"mode": "patch", "patch": patch, "reason": "Test"})
        self.assertFalse(out["allowed"])
        self.assertEqual(len(bridge.requests), 2)

    def test_bridge_error_uses_error_status(self) -> None:
        from hermes_adapter.service import ValidateService

        class BrokenBridge:
            def validate(self, request: dict[str, Any]) -> dict[str, Any]:
                raise RuntimeError("bridge down")

            def close(self) -> None:
                return None

        service = ValidateService(bridge=BrokenBridge())  # type: ignore[arg-type]
        out = service.validate_tool("terminal", {"command": "echo x", "reason": "Bridge test"})
        self.assertFalse(out["allowed"])
        self.assertEqual(out["agent_response"]["status"], "error")
        self.assertEqual(out["agent_response"]["exit_code"], -1)


class TestServer(unittest.TestCase):
    def test_validate_tool_endpoint(self) -> None:
        import asyncio

        import httpx
        from httpx import ASGITransport

        from hermes_adapter.server import create_app
        from hermes_adapter.service import ValidateService

        bridge = FakeBridge({"allowed": True, "success": True, "validated_only": True})
        app = create_app(service=ValidateService(bridge=bridge))  # type: ignore[arg-type]

        async def call_validate_tool() -> httpx.Response:
            transport = ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://hermes-adapter",
            ) as client:
                return await client.post(
                    "/validate-tool",
                    json={
                        "tool": "terminal",
                        "args": {"command": "echo ok", "reason": "Server test"},
                    },
                )

        resp = asyncio.run(call_validate_tool())
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["allowed"])


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
