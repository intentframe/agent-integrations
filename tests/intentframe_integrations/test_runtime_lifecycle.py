#!/usr/bin/env python3
"""Tests for runtime ownership and backend readiness."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.integration_pack import load_integration_pack  # noqa: E402
from intentframe_integrations.runtime_lifecycle import (  # noqa: E402
    backend_ready_for_pack,
    bridge_serves_pack,
    ensure_backend_for_pack,
    iter_agent_configs,
)


def _write_agent(path: Path, *, agent_id: str, secret: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "agent_id": agent_id,
                "user_id": "test_user",
                "agent_type": agent_id,
                "action_types": ["RUN_COMMAND"],
                "bridge_secret": secret,
                "policy_file": "policy.yaml",
            }
        ),
        encoding="utf-8",
    )
    return path


class TestIterAgentConfigs(unittest.TestCase):
    def test_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = _write_agent(Path(tmp) / "agent.json", agent_id="a", secret="s")
            self.assertEqual(iter_agent_configs(cfg), [cfg.resolve()])

    def test_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            a = _write_agent(root / "one" / "agent.json", agent_id="one", secret="s1")
            b = _write_agent(root / "two" / "agent.json", agent_id="two", secret="s2")
            self.assertEqual(iter_agent_configs(root), [a.resolve(), b.resolve()])


class TestBridgeServesPack(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")

    @patch("intentframe_integrations.runtime_lifecycle.is_bridge_running", return_value=False)
    def test_bridge_not_running(self, _mock: object) -> None:
        self.assertFalse(bridge_serves_pack(self.pack))

    @patch("intentframe_integrations.runtime_lifecycle.load_bridge_agents")
    @patch("intentframe_integrations.runtime_lifecycle.is_bridge_running", return_value=True)
    def test_agent_missing(self, _running: object, load_agents: object) -> None:
        load_agents.return_value = {}
        self.assertFalse(bridge_serves_pack(self.pack))

    @patch("intentframe_integrations.runtime_lifecycle.load_bridge_agents")
    @patch("intentframe_integrations.runtime_lifecycle.is_bridge_running", return_value=True)
    def test_secret_mismatch(self, _running: object, load_agents: object) -> None:
        from if_security_backend.bridge.config import BridgeAgentConfig

        load_agents.return_value = {
            "hermes": BridgeAgentConfig(
                agent_id="hermes",
                secret="wrong-secret",
                user_id="dev_user",
                agent_type="hermes",
                action_types=("RUN_COMMAND",),
            )
        }
        self.assertFalse(bridge_serves_pack(self.pack))

    @patch("intentframe_integrations.runtime_lifecycle.load_bridge_agents")
    @patch("intentframe_integrations.runtime_lifecycle.is_bridge_running", return_value=True)
    def test_secret_match(self, _running: object, load_agents: object) -> None:
        from if_security_backend.bridge.config import BridgeAgentConfig

        load_agents.return_value = {
            "hermes": BridgeAgentConfig(
                agent_id="hermes",
                secret=self.pack.agent.bridge_secret,
                user_id="dev_user",
                agent_type="hermes",
                action_types=("RUN_COMMAND",),
            )
        }
        self.assertTrue(bridge_serves_pack(self.pack))


class TestEnsureBackendForPack(unittest.TestCase):
    def setUp(self) -> None:
        self.pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")

    @patch("intentframe_integrations.runtime_lifecycle.backend_ready_for_pack", return_value=True)
    def test_already_ready(self, _mock: object) -> None:
        ok, err, started = ensure_backend_for_pack(self.pack, run_backend_start=lambda _a: 1)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertFalse(started)

    @patch("intentframe_integrations.runtime_lifecycle.bridge_serves_pack", return_value=False)
    @patch("intentframe_integrations.runtime_lifecycle.is_bridge_running", return_value=True)
    @patch("intentframe_integrations.runtime_lifecycle.core_healthy", return_value=True)
    def test_wrong_bridge_config(self, *_mocks: object) -> None:
        ok, err, started = ensure_backend_for_pack(self.pack, run_backend_start=lambda _a: 0)
        self.assertFalse(ok)
        self.assertIn("does not match", err or "")
        self.assertFalse(started)

    @patch("intentframe_integrations.runtime_lifecycle.is_bridge_running", return_value=False)
    @patch("intentframe_integrations.runtime_lifecycle.core_healthy", return_value=False)
    @patch("intentframe_integrations.runtime_lifecycle.backend_ready_for_pack")
    def test_starts_backend_when_needed(
        self,
        ready_mock: object,
        _core_mock: object,
        _bridge_mock: object,
    ) -> None:
        """Hermetic: no live e2e runtime; exercises the full-start branch only."""
        ready_mock.side_effect = [False, True]
        calls: list[list[str]] = []

        def fake_start(argv: list[str]) -> int:
            calls.append(argv)
            return 0

        ok, err, started = ensure_backend_for_pack(self.pack, run_backend_start=fake_start)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertTrue(started)
        self.assertEqual(len(calls), 1)
        self.assertIn("--agent-config", calls[0])
        self.assertIn(str(self.pack.agent.source_path), calls[0])


class TestBackendReadyForPack(unittest.TestCase):
    @patch("intentframe_integrations.runtime_lifecycle.bridge_serves_pack", return_value=True)
    @patch("intentframe_integrations.runtime_lifecycle.is_bridge_running", return_value=True)
    @patch("intentframe_integrations.runtime_lifecycle.core_healthy", return_value=True)
    def test_all_signals_true(self, *_mocks: object) -> None:
        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        self.assertTrue(backend_ready_for_pack(pack))


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
