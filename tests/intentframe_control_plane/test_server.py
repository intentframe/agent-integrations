"""API tests for control plane server."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from intentframe_control_plane.cli_runner import CliResult
from intentframe_control_plane.server import app


class TestControlPlaneApi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(app)

    def test_health(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["service"], "intentframe-control-plane")
        self.assertEqual(body["data"]["status"], "ok")

    def test_health_fast_with_pid_file(self) -> None:
        import os
        import tempfile
        import time
        from pathlib import Path
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            pid_path = Path(tmp) / "control-plane.pid"
            pid_path.write_text(str(os.getpid()), encoding="utf-8")
            with patch("intentframe_control_plane.config.PID_FILE", pid_path):
                start = time.monotonic()
                resp = self.client.get("/api/health")
                elapsed = time.monotonic() - start
            self.assertEqual(resp.status_code, 200)
            self.assertLess(elapsed, 0.5)
            self.assertEqual(resp.json()["data"]["status"], "ok")

    def test_status_json(self) -> None:
        resp = self.client.get("/api/status")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIn("control_plane", body["data"])
        self.assertIn("bridge_present", body["data"])

    def test_governance_read(self) -> None:
        resp = self.client.get("/api/governance")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["data"]["agent"], "hermes")
        self.assertIn("tools", body["data"])

    def test_policy_read(self) -> None:
        resp = self.client.get("/api/policy")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIn("meta", body["data"])
        self.assertIn("yaml", body["data"])

    def test_config(self) -> None:
        resp = self.client.get("/api/config")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])
        self.assertIn("hermes_chat_url", body["data"])

    @patch("intentframe_control_plane.server.run_cli")
    def test_stack_stop_requires_confirm(self, mock_run) -> None:
        resp = self.client.post("/api/stack/stop")
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertFalse(body["ok"])
        self.assertIn("error", body)
        mock_run.assert_not_called()

    @patch("intentframe_control_plane.server.run_cli")
    def test_stack_stop_with_confirm(self, mock_run) -> None:
        mock_run.return_value = CliResult(
            argv=["intentframe-integrations", "stop"],
            returncode=0,
            stdout="stopped",
            stderr="",
        )
        resp = self.client.post("/api/stack/stop", headers={"X-Confirm": "true"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["ok"])

    def test_spa_fallback(self) -> None:
        from intentframe_control_plane.server import INDEX_HTML

        if not INDEX_HTML.is_file():
            self.skipTest("frontend not built")
        resp = self.client.get("/governance")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))


if __name__ == "__main__":
    unittest.main()
