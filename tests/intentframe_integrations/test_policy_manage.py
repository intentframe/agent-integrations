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
GOVERNANCE_TEMPLATE = REPO_ROOT / "integrations" / "hermes" / "governance" / "tools.yaml"
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
    validate_policy_file,
)


class patch_home:
    def __init__(self, home: Path) -> None:
        self.home = home
        self._previous: str | None = None
        self._gov_previous: str | None = None
        self._manifest_previous: str | None = None

    def __enter__(self) -> None:
        self._previous = os.environ.get("HOME")
        self._gov_previous = os.environ.get("HERMES_GOVERNANCE_YAML")
        self._manifest_previous = os.environ.get("IF_DYNAMIC_BUNDLE_MANIFEST")
        os.environ["HOME"] = str(self.home)
        os.environ["HERMES_GOVERNANCE_YAML"] = str(GOVERNANCE_TEMPLATE)
        manifest_dir = (
            self.home / ".intentframe" / "integrations" / "hermes" / "governance"
        )
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "generic_actions.manifest"
        manifest_path.write_text("HERMES_CRONJOB", encoding="utf-8")
        os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = str(manifest_path)
        self._reset_bundle_loader_state()
        return self

    def __exit__(self, *args: object) -> None:
        self._reset_bundle_loader_state()
        if self._manifest_previous is None:
            os.environ.pop("IF_DYNAMIC_BUNDLE_MANIFEST", None)
        else:
            os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = self._manifest_previous
        if self._gov_previous is None:
            os.environ.pop("HERMES_GOVERNANCE_YAML", None)
        else:
            os.environ["HERMES_GOVERNANCE_YAML"] = self._gov_previous
        if self._previous is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._previous

    @staticmethod
    def _reset_bundle_loader_state() -> None:
        import intentframe_bundle_sdk.loader as bundle_loader
        import intentframe_bundle_sdk.registry as registry

        bundle_loader._LOADED_PACKAGES = None
        registry._ACTION_BY_ID.clear()
        registry._ACTION_INSTANCES.clear()
        registry._DOMAIN_BY_ID.clear()
        registry._ACTION_TO_DOMAINS.clear()
        registry._ROUTED_DOMAIN_IDS = frozenset()


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
            validate_policy_file(self.pack, bad)

    @patch("if_security_backend.runtime.policy.seed_policy")
    def test_set_bad_policy_preserves_runtime(self, seed_mock: object) -> None:
        bad = Path(self.temp_dir.name) / "bad-policy.yaml"
        bad.write_text("agent_id: not_hermes\nallowed_actions: {}\n", encoding="utf-8")
        with patch_home(self.home):
            runtime = ensure_runtime_policy_yaml(self.pack)
            original = runtime.read_text(encoding="utf-8")
            with self.assertRaises(PolicyError):
                policy_set("hermes", bad)
            self.assertEqual(runtime.read_text(encoding="utf-8"), original)
        seed_mock.assert_not_called()

    @patch("if_security_backend.runtime.policy.seed_policy")
    def test_set_missing_source_preserves_runtime(self, seed_mock: object) -> None:
        missing = Path(self.temp_dir.name) / "missing-policy.yaml"
        with patch_home(self.home):
            runtime = ensure_runtime_policy_yaml(self.pack)
            original = runtime.read_text(encoding="utf-8")
            with self.assertRaises(PolicyError):
                policy_set("hermes", missing)
            self.assertEqual(runtime.read_text(encoding="utf-8"), original)
        seed_mock.assert_not_called()

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

    @patch(
        "intentframe_integrations.policy_manage.shipped_policy_template_path",
        side_effect=FileNotFoundError("Shipped policy template missing"),
    )
    def test_show_missing_shipped_template_raises_policy_error(self, _mock: object) -> None:
        with patch_home(self.home):
            with self.assertRaises(PolicyError):
                policy_show("hermes")

    @patch(
        "intentframe_integrations.policy_manage.ensure_runtime_policy_yaml",
        side_effect=FileNotFoundError("Shipped policy template missing"),
    )
    def test_reload_missing_template_raises_policy_error(self, _mock: object) -> None:
        with self.assertRaises(PolicyError):
            policy_reload("hermes")

    @patch(
        "intentframe_integrations.policy_manage.reset_runtime_policy_yaml",
        side_effect=FileNotFoundError("Shipped policy template missing"),
    )
    def test_reset_missing_template_raises_policy_error(self, _mock: object) -> None:
        with self.assertRaises(PolicyError):
            policy_reset("hermes")


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

    @patch(
        "intentframe_integrations.cli.policy_reload",
        side_effect=PolicyError("Shipped policy template missing"),
    )
    def test_cli_policy_reload_reports_error(self, _mock: object) -> None:
        from intentframe_integrations.cli import main

        ec = main(["policy", "reload", "hermes"])
        self.assertEqual(ec, 1)

    @patch(
        "intentframe_integrations.cli.policy_set",
        side_effect=PolicyError("Policy agent_id mismatch"),
    )
    def test_cli_policy_set_reports_error(self, _mock: object) -> None:
        from intentframe_integrations.cli import main

        ec = main(["policy", "set", "hermes", "/tmp/bad.yaml"])
        self.assertEqual(ec, 1)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
