#!/usr/bin/env python3
"""Live integration: hermes adapter against IntentFrame backend bridge."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from live_fixtures import (  # noqa: E402
    DELETE_ALLOW_ARGS,
    DELETE_BLOCK_ARGS,
    PATCH_ALLOW_REPLACE_ARGS,
    PATCH_BLOCK_REPLACE_ARGS,
    PATCH_V4A_BLOCK_ARGS,
    PATCH_V4A_MIXED_ALLOW_ARGS,
    PROCESS_ALLOW_ARGS,
    PROCESS_BLOCK_ARGS,
    WRITE_ALLOW_ARGS,
    WRITE_BLOCK_ARGS,
)


class TestLiveHermesAdapter(unittest.TestCase):
    def setUp(self) -> None:
        socket = os.environ.get("IF_AGENT_ADAPTER_SOCKET")
        if not socket:
            self.skipTest("IF_AGENT_ADAPTER_SOCKET not set")
        expanded = os.path.expanduser(socket)
        if not os.path.exists(expanded):
            self.skipTest(f"adapter socket missing: {expanded}")
        transport = httpx.HTTPTransport(uds=expanded)
        self.client = httpx.Client(
            transport=transport,
            base_url="http://hermes-adapter",
            timeout=120.0,
        )

    def tearDown(self) -> None:
        self.client.close()

    def _validate_tool(self, tool: str, args: dict[str, object]) -> dict[str, object]:
        resp = self.client.post("/validate-tool", json={"tool": tool, "args": args})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsInstance(body, dict)
        return body

    def test_health(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("adapter"), "hermes")

    def test_allow_terminal(self) -> None:
        body = self._validate_tool(
            "terminal",
            {"command": "echo hermes-adapter-ok", "reason": "Live allow test"},
        )
        self.assertTrue(body["allowed"])

    def test_block_terminal(self) -> None:
        body = self._validate_tool(
            "terminal",
            {"command": "sudo rm -rf /", "reason": "Should block"},
        )
        self.assertFalse(body["allowed"])
        self.assertIn("agent_response", body)

    def test_allow_process(self) -> None:
        body = self._validate_tool("process", PROCESS_ALLOW_ARGS)
        self.assertTrue(body["allowed"])

    def test_block_process(self) -> None:
        body = self._validate_tool("process", PROCESS_BLOCK_ARGS)
        self.assertFalse(body["allowed"])
        self.assertIn("agent_response", body)

    def test_allow_write_file(self) -> None:
        body = self._validate_tool("write_file", WRITE_ALLOW_ARGS)
        self.assertTrue(body["allowed"])

    def test_block_write_file(self) -> None:
        body = self._validate_tool("write_file", WRITE_BLOCK_ARGS)
        self.assertFalse(body["allowed"])
        self.assertIn("agent_response", body)

    def test_allow_delete_file(self) -> None:
        body = self._validate_tool("delete_file", DELETE_ALLOW_ARGS)
        self.assertTrue(body["allowed"])

    def test_block_delete_file(self) -> None:
        body = self._validate_tool("delete_file", DELETE_BLOCK_ARGS)
        self.assertFalse(body["allowed"])
        self.assertIn("agent_response", body)

    def test_allow_patch_replace(self) -> None:
        body = self._validate_tool("patch", PATCH_ALLOW_REPLACE_ARGS)
        self.assertTrue(body["allowed"])

    def test_block_patch_replace(self) -> None:
        body = self._validate_tool("patch", PATCH_BLOCK_REPLACE_ARGS)
        self.assertFalse(body["allowed"])
        self.assertIn("agent_response", body)

    def test_allow_patch_v4a_mixed(self) -> None:
        body = self._validate_tool("patch", PATCH_V4A_MIXED_ALLOW_ARGS)
        self.assertTrue(body["allowed"])

    def test_block_patch_v4a_mixed_system_delete(self) -> None:
        body = self._validate_tool("patch", PATCH_V4A_BLOCK_ARGS)
        self.assertFalse(body["allowed"])
        self.assertIn("agent_response", body)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
