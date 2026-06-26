#!/usr/bin/env python3
"""Tests for ``intentframe-integrations up hermes`` (chat-ready stack)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.cli import _cmd_up  # noqa: E402
from intentframe_integrations.integration_pack import load_integration_pack  # noqa: E402


class TestCmdUp(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    @patch("intentframe_integrations.cli._gateway_status_line", return_value="gateway: running")
    @patch("intentframe_integrations.cli.start_hermes_gateway")
    @patch("intentframe_integrations.cli.resolve_hermes_bin")
    @patch("intentframe_integrations.cli._start_pack", return_value=0)
    @patch("intentframe_integrations.cli.load_and_activate_pack")
    def test_up_starts_runtime_then_gateway(
        self,
        load_mock: MagicMock,
        start_pack_mock: MagicMock,
        resolve_mock: MagicMock,
        gateway_mock: MagicMock,
        _status_mock: MagicMock,
    ) -> None:
        load_mock.return_value = self.pack
        resolve_mock.return_value = Path("/usr/local/bin/hermes")

        self.assertEqual(_cmd_up("hermes", seed=True, skip_if_exists=False), 0)

        load_mock.assert_called_once_with("hermes")
        start_pack_mock.assert_called_once_with(self.pack, seed=True, skip_if_exists=False)
        gateway_mock.assert_called_once_with(self.pack)
        resolve_mock.assert_called_once()

    def test_up_requires_openai_api_key(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(_cmd_up("hermes", seed=False, skip_if_exists=False), 1)

    def test_up_rejects_non_hermes_agent(self) -> None:
        self.assertEqual(_cmd_up("openclaw", seed=False, skip_if_exists=False), 1)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    @patch("intentframe_integrations.cli._rollback_start")
    @patch("intentframe_integrations.cli.resolve_hermes_bin", return_value=None)
    @patch("intentframe_integrations.cli._start_pack", return_value=0)
    @patch("intentframe_integrations.cli.load_and_activate_pack")
    def test_up_rolls_back_when_hermes_missing(
        self,
        load_mock: MagicMock,
        _start_pack_mock: MagicMock,
        _resolve_mock: MagicMock,
        rollback_mock: MagicMock,
    ) -> None:
        load_mock.return_value = self.pack
        self.assertEqual(_cmd_up("hermes", seed=False, skip_if_exists=False), 1)
        rollback_mock.assert_called_once_with(self.pack)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    @patch("intentframe_integrations.cli._rollback_start")
    @patch("intentframe_integrations.cli.start_hermes_gateway")
    @patch("intentframe_integrations.cli.resolve_hermes_bin")
    @patch("intentframe_integrations.cli._start_pack", return_value=0)
    @patch("intentframe_integrations.cli.load_and_activate_pack")
    def test_up_rolls_back_when_gateway_fails(
        self,
        load_mock: MagicMock,
        _start_pack_mock: MagicMock,
        resolve_mock: MagicMock,
        gateway_mock: MagicMock,
        rollback_mock: MagicMock,
    ) -> None:
        from intentframe_integrations.hermes_gateway import HermesGatewayError

        load_mock.return_value = self.pack
        resolve_mock.return_value = Path("/usr/local/bin/hermes")
        gateway_mock.side_effect = HermesGatewayError("gateway boom")

        self.assertEqual(_cmd_up("hermes", seed=False, skip_if_exists=False), 1)
        rollback_mock.assert_called_once_with(self.pack)

    @patch.dict("os.environ", {"OPENAI_API_KEY": "sk-test"}, clear=False)
    @patch("intentframe_integrations.cli.start_hermes_gateway")
    @patch("intentframe_integrations.cli.resolve_hermes_bin")
    @patch("intentframe_integrations.cli._start_pack", return_value=1)
    @patch("intentframe_integrations.cli.load_and_activate_pack")
    def test_up_skips_gateway_when_start_pack_fails(
        self,
        load_mock: MagicMock,
        _start_pack_mock: MagicMock,
        resolve_mock: MagicMock,
        gateway_mock: MagicMock,
    ) -> None:
        load_mock.return_value = self.pack
        self.assertEqual(_cmd_up("hermes", seed=False, skip_if_exists=False), 1)
        resolve_mock.assert_not_called()
        gateway_mock.assert_not_called()


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
