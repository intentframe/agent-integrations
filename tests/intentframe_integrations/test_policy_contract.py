#!/usr/bin/env python3
"""Tests for runtime policy.yaml materialization."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.integration_pack import load_integration_pack  # noqa: E402
from intentframe_integrations.policy_contract import (  # noqa: E402
    ensure_runtime_policy_yaml,
    install_policy_from_path,
    policy_yaml_runtime_path,
    reset_runtime_policy_yaml,
    shipped_policy_template_path,
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


class TestPolicyContract(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name) / "home"
        self.home.mkdir()
        self.pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_shipped_template_exists(self) -> None:
        path = shipped_policy_template_path(self.pack)
        self.assertTrue(path.is_file())
        self.assertEqual(path.name, "policy.yaml")

    def test_ensure_copies_once(self) -> None:
        with patch_home(self.home):
            first = ensure_runtime_policy_yaml(self.pack)
            second = ensure_runtime_policy_yaml(self.pack)
            self.assertEqual(first, second)
            self.assertEqual(
                first,
                policy_yaml_runtime_path("hermes"),
            )
            self.assertTrue(first.is_file())

            shipped = shipped_policy_template_path(self.pack)
            self.assertEqual(
                first.read_text(encoding="utf-8"),
                shipped.read_text(encoding="utf-8"),
            )

    def test_ensure_does_not_overwrite_user_edits(self) -> None:
        with patch_home(self.home):
            path = ensure_runtime_policy_yaml(self.pack)
            path.write_text("user-edit: true\n", encoding="utf-8")
            again = ensure_runtime_policy_yaml(self.pack)
            self.assertEqual(again.read_text(encoding="utf-8"), "user-edit: true\n")

    def test_reset_overwrites_runtime(self) -> None:
        with patch_home(self.home):
            path = ensure_runtime_policy_yaml(self.pack)
            path.write_text("user-edit: true\n", encoding="utf-8")
            reset = reset_runtime_policy_yaml(self.pack)
            shipped = shipped_policy_template_path(self.pack)
            self.assertEqual(
                reset.read_text(encoding="utf-8"),
                shipped.read_text(encoding="utf-8"),
            )

    def test_install_from_external_path(self) -> None:
        custom = Path(self.temp_dir.name) / "custom-policy.yaml"
        custom.write_text(
            shipped_policy_template_path(self.pack).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        with patch_home(self.home):
            dest = install_policy_from_path(self.pack, custom)
            self.assertEqual(dest, policy_yaml_runtime_path("hermes"))
            self.assertEqual(
                dest.read_text(encoding="utf-8"),
                custom.read_text(encoding="utf-8"),
            )


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
