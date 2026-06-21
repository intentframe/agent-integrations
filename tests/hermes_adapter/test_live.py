#!/usr/bin/env python3
"""Live integration: hermes adapter against IntentFrame backend bridge."""

from __future__ import annotations

import os
import sys
import unittest

import httpx


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

    def test_health(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("adapter"), "hermes")

    def test_allow_benign(self) -> None:
        resp = self.client.post(
            "/validate-tool",
            json={
                "tool": "terminal",
                "args": {"command": "echo hermes-adapter-ok", "reason": "Live allow test"},
            },
        )
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["allowed"])

    def test_block_dangerous(self) -> None:
        resp = self.client.post(
            "/validate-tool",
            json={
                "tool": "terminal",
                "args": {"command": "sudo rm -rf /", "reason": "Should block"},
            },
        )
        body = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(body["allowed"])
        self.assertIn("agent_response", body)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
