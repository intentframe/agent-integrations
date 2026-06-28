"""Unit tests for control plane lifecycle."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from intentframe_control_plane.config import ControlPlaneSettings, validate_bind_host
from intentframe_control_plane.lifecycle import format_status_line, control_plane_status


class TestControlPlaneConfig(unittest.TestCase):
    def test_validate_loopback_ok(self) -> None:
        validate_bind_host("127.0.0.1", allow_remote=False)

    def test_validate_remote_blocked(self) -> None:
        with self.assertRaises(ValueError):
            validate_bind_host("0.0.0.0", allow_remote=False)

    def test_validate_remote_allowed(self) -> None:
        validate_bind_host("0.0.0.0", allow_remote=True)


class TestControlPlaneStatus(unittest.TestCase):
    @patch("intentframe_control_plane.lifecycle._health_check", return_value=False)
    @patch("intentframe_control_plane.lifecycle._read_pid", return_value=None)
    def test_status_stopped(self, _pid, _health) -> None:
        status = control_plane_status(
            ControlPlaneSettings(host="127.0.0.1", port=9720, token=None, allow_remote=False)
        )
        self.assertFalse(status.running)
        self.assertIn("9720", status.url)

    @patch("intentframe_control_plane.lifecycle._health_check", return_value=True)
    @patch("intentframe_control_plane.lifecycle._pid_alive", return_value=True)
    @patch("intentframe_control_plane.lifecycle._read_pid", return_value=4242)
    def test_status_running(self, _pid, _alive, _health) -> None:
        status = control_plane_status(
            ControlPlaneSettings(host="127.0.0.1", port=9720, token=None, allow_remote=False)
        )
        self.assertTrue(status.running)
        self.assertTrue(status.healthy)
        line = format_status_line(status)
        self.assertIn("control-plane: running", line)


class TestStartControlPlaneCleanup(unittest.TestCase):
    @patch("intentframe_control_plane.lifecycle._kill_pid")
    @patch("intentframe_control_plane.lifecycle._terminate_pid")
    @patch("intentframe_control_plane.lifecycle._health_check", return_value=False)
    @patch("intentframe_control_plane.lifecycle._pid_alive", return_value=True)
    @patch("intentframe_control_plane.lifecycle.subprocess.Popen")
    @patch("intentframe_control_plane.lifecycle.control_plane_status")
    @patch("intentframe_control_plane.lifecycle.time.monotonic", side_effect=[0.0, 0.0, 31.0, 31.0, 36.0, 36.0, 41.0])
    def test_start_timeout_kills_child(
        self,
        _monotonic,
        mock_status,
        mock_popen,
        _alive,
        _health,
        mock_terminate,
        mock_kill,
    ) -> None:
        import tempfile
        from pathlib import Path

        from intentframe_control_plane.lifecycle import ControlPlaneError, start_control_plane

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "control-plane.log"
            pid_path = Path(tmp) / "control-plane.pid"
            mock_status.return_value.running = False
            mock_status.return_value.healthy = False
            proc = mock_popen.return_value
            proc.pid = 9999

            with patch("intentframe_control_plane.lifecycle.LOG_FILE", log_path):
                with patch("intentframe_control_plane.lifecycle.PID_FILE", pid_path):
                    with patch("intentframe_control_plane.lifecycle.time.sleep"):
                        with self.assertRaises(ControlPlaneError):
                            start_control_plane(quiet=True)

            mock_terminate.assert_called_once_with(9999)
            mock_kill.assert_called_once_with(9999)
            self.assertFalse(pid_path.exists())


if __name__ == "__main__":
    unittest.main()
