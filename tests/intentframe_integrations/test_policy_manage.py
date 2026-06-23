#!/usr/bin/env python3
"""Tests for policy show/set/reload/reset and CLI wiring."""

from __future__ import annotations

import os
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
from intentframe_integrations.policy_contract import (  # noqa: E402
    ensure_runtime_policy_yaml,
    policy_yaml_runtime_path,
    shipped_policy_template_path,
)
from intentframe_integrations.policy_manage import (  # noqa: E402
    PolicyError,
    policy_reload,
    policy_reset,
    policy_set,
    policy_show,
    seed_agent_policy_from_file,
)


class patch_home:
    def __init__(self, home: Path) -> None:
        self.home = home
        self._previous: str | None = None

    def __enter__(self) -> None:
        self._previous = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)
        return self

    def __exit__(self, *args: object) -> None:
        if self._previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._previous


class TestPolicyManage(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name) / "home"
        self.home.mkdir()
        self.pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_validate_rejects_agent_id_mismatch(self) -> None:
        bad = Path(self.temp_dir.name) / "bad-policy.yaml"
        bad.write_text("agent_id: not_hermes\nallowed_actions: {}\n", encoding="utf-8")
        with self.assertRaises(PolicyError):
            seed_agent_policy_from_file(self.pack, bad)

    @patch("if_security_backend.runtime.policy.seed_policy")
    def test_reload_calls_seed(self, seed_mock: object) -> None:
        with patch_home(self.home):
            runtime = ensure_runtime_policy_yaml(self.pack)
            path = policy_reload("hermes")
            self.assertEqual(path, runtime)
            seed_mock.assert_called_once()

    @patch("if_security_backend.runtime.policy.seed_policy")
    def test_set_installs_and_seeds(self, seed_mock: object) -> None:
        custom = Path(self.temp_dir.name) / "custom.yaml"
        custom.write_text(
            shipped_policy_template_path(self.pack).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        with patch_home(self.home):
            path = policy_set("hermes", custom)
            self.assertEqual(path, policy_yaml_runtime_path("hermes"))
            self.assertTrue(path.is_file())
            seed_mock.assert_called_once()

    @patch("if_security_backend.runtime.policy.seed_policy")
    def test_reset_restores_shipped_and_seeds(self, seed_mock: object) -> None:
        with patch_home(self.home):
            runtime = ensure_runtime_policy_yaml(self.pack)
            runtime.write_text("user-edit: true\n", encoding="utf-8")
            path = policy_reset("hermes")
            shipped = shipped_policy_template_path(self.pack)
            self.assertEqual(path.read_text(encoding="utf-8"), shipped.read_text(encoding="utf-8"))
            seed_mock.assert_called_once()

    def test_show_reports_runtime_path(self) -> None:
        with patch_home(self.home):
            ensure_runtime_policy_yaml(self.pack)
            report = policy_show("hermes")
            self.assertEqual(report.runtime_path, policy_yaml_runtime_path("hermes"))
            self.assertTrue(report.runtime_exists)


class TestPolicyCli(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @patch("if_security_backend.runtime.policy.seed_policy")
    def test_cli_policy_reload(self, seed_mock: object) -> None:
        from intentframe_integrations.cli import main

        with patch_home(self.home):
            pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
            ensure_runtime_policy_yaml(pack)
            ec = main(["policy", "reload", "hermes"])
        self.assertEqual(ec, 0)
        seed_mock.assert_called_once()

    @patch("intentframe_integrations.cli.policy_set")
    def test_cli_policy_set(self, set_mock: object) -> None:
        from intentframe_integrations.cli import main

        custom = Path(self.temp_dir.name) / "custom.yaml"
        custom.write_text("agent_id: hermes\n", encoding="utf-8")
        set_mock.return_value = policy_yaml_runtime_path("hermes")
        ec = main(["policy", "set", "hermes", str(custom)])
        self.assertEqual(ec, 0)
        set_mock.assert_called_once()

    def test_cli_seed_passes_runtime_policy_path(self) -> None:
        from intentframe_integrations.cli import main

        with patch_home(self.home):
            pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
            runtime = ensure_runtime_policy_yaml(pack)
            with patch("intentframe_integrations.cli._run_backend") as backend_mock:
                backend_mock.return_value = 0
                ec = main(["seed", "hermes"])
        self.assertEqual(ec, 0)
        argv = backend_mock.call_args[0][0]
        self.assertIn("--policy", argv)
        self.assertIn(str(runtime), argv)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
