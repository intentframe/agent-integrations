#!/usr/bin/env python3
"""Tests for CLI start/ensure runtime behavior (mocked backend)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.cli import _ensure_runtime, _start_pack  # noqa: E402
from intentframe_integrations.integration_pack import load_integration_pack  # noqa: E402


class TestStartPackRollback(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")

    @patch("intentframe_integrations.cli._run_backend")
    @patch("intentframe_integrations.cli._start_adapter_for_pack", return_value=1)
    @patch("intentframe_integrations.cli.ensure_backend_for_pack")
    def test_rolls_back_backend_when_adapter_fails(
        self,
        ensure_mock: object,
        _adapter_mock: object,
        backend_mock: object,
    ) -> None:
        ensure_mock.return_value = (True, None, True)
        ec = _start_pack(self.pack, seed=False, skip_if_exists=False)
        self.assertEqual(ec, 1)
        backend_mock.assert_called_with(["stop"])

    @patch("intentframe_integrations.cli._start_adapter_for_pack", return_value=0)
    @patch("intentframe_integrations.cli.ensure_backend_for_pack")
    def test_succeeds_when_backend_already_ready(
        self,
        ensure_mock: object,
        _adapter_mock: object,
    ) -> None:
        ensure_mock.return_value = (True, None, False)
        ec = _start_pack(self.pack, seed=False, skip_if_exists=False)
        self.assertEqual(ec, 0)


class TestEnsureRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")

    @patch("intentframe_integrations.cli.is_adapter_running", return_value=True)
    @patch("intentframe_integrations.cli.backend_ready_for_pack", return_value=True)
    def test_noop_when_ready(self, *_mocks: object) -> None:
        self.assertEqual(_ensure_runtime(self.pack), 0)

    @patch("intentframe_integrations.cli._start_adapter_for_pack", return_value=0)
    @patch("intentframe_integrations.cli.is_adapter_running", return_value=False)
    @patch("intentframe_integrations.cli.ensure_backend_for_pack")
    @patch("intentframe_integrations.cli.backend_ready_for_pack")
    def test_starts_adapter_when_backend_ready(
        self,
        ready_mock: object,
        ensure_mock: object,
        _adapter_running: object,
        adapter_start: object,
    ) -> None:
        ready_mock.side_effect = [False, True]
        ensure_mock.return_value = (True, None, False)
        self.assertEqual(_ensure_runtime(self.pack), 0)
        adapter_start.assert_called_once()

    @patch("intentframe_integrations.cli.ensure_backend_for_pack")
    @patch("intentframe_integrations.cli.backend_ready_for_pack", return_value=False)
    def test_fails_on_bridge_mismatch(self, ready_mock: object, ensure_mock: object) -> None:
        ensure_mock.return_value = (False, "bridge mismatch", False)
        self.assertEqual(_ensure_runtime(self.pack), 1)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
