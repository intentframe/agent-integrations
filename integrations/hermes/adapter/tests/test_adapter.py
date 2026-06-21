#!/usr/bin/env python3
"""Unit tests for hermes-adapter mapper and service."""

from __future__ import annotations

import sys
import unittest
from typing import Any


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

        req = map_terminal({"command": "echo hi", "reason": "List files"})
        self.assertEqual(req["action"], "RUN_COMMAND")
        self.assertEqual(req["command"], "echo hi")
        self.assertEqual(req["reason"], "List files")

    def test_missing_reason(self) -> None:
        from hermes_adapter.mapper import ValidationError, map_terminal

        with self.assertRaises(ValidationError):
            map_terminal({"command": "echo hi"})


class TestValidateService(unittest.TestCase):
    def test_allow(self) -> None:
        from hermes_adapter.bridge_session import BridgeSession
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
