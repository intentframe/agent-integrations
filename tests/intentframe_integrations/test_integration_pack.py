#!/usr/bin/env python3
"""Tests for integration pack parsing."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.hermes_governance_contract import (  # noqa: E402
    actions_manifest_runtime_path,
)
from intentframe_integrations.integration_pack import (  # noqa: E402
    load_and_activate_pack,
    load_integration_pack,
)


class TestIntegrationPack(unittest.TestCase):
    def test_hermes_adapter_defaults(self) -> None:
        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        self.assertIsNotNone(pack.adapter)
        assert pack.adapter is not None
        self.assertEqual(pack.adapter.python, "3.12")
        self.assertEqual(pack.adapter.module, "hermes_adapter.main")
        self.assertTrue(pack.adapter.source_dir.is_dir())

    def test_custom_adapter_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "agent.json"
            cfg.write_text(
                json.dumps(
                    {
                        "agent_id": "custom",
                        "user_id": "u",
                        "bridge_secret": "secret",
                        "adapter": {
                            "runtime": "python",
                            "python": "3.11",
                            "module": "custom_adapter.main",
                            "source": "adapter",
                            "socket": "/tmp/custom.sock",
                        },
                    }
                ),
                encoding="utf-8",
            )
            (Path(tmp) / "adapter").mkdir()
            pack = load_integration_pack(cfg)
            assert pack.adapter is not None
            self.assertEqual(pack.adapter.python, "3.11")
            self.assertEqual(pack.adapter.module, "custom_adapter.main")


class TestLoadAndActivatePack(unittest.TestCase):
    """Regression: pack activation env parity (setdefault + manifest seeding)."""
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name) / "home"
        self.home.mkdir()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_load_and_activate_applies_agent_json_env_with_setdefault(self) -> None:
        override = "/tmp/custom-manifest.manifest"
        previous_home = os.environ.get("HOME")
        previous_manifest = os.environ.get("IF_DYNAMIC_BUNDLE_MANIFEST")
        try:
            os.environ["HOME"] = str(self.home)
            os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = override
            load_and_activate_pack("hermes")
            self.assertEqual(os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"], override)
        finally:
            if previous_manifest is None:
                os.environ.pop("IF_DYNAMIC_BUNDLE_MANIFEST", None)
            else:
                os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = previous_manifest
            if previous_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous_home

    def test_load_and_activate_seeds_manifest_when_missing(self) -> None:
        previous_home = os.environ.get("HOME")
        previous_manifest = os.environ.get("IF_DYNAMIC_BUNDLE_MANIFEST")
        try:
            os.environ["HOME"] = str(self.home)
            os.environ.pop("IF_DYNAMIC_BUNDLE_MANIFEST", None)
            load_and_activate_pack("hermes")
            expected = actions_manifest_runtime_path("hermes")
            self.assertTrue(expected.is_file())
            self.assertIn("HERMES_CRONJOB", expected.read_text(encoding="utf-8"))
            self.assertEqual(os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"], str(expected))
        finally:
            if previous_manifest is None:
                os.environ.pop("IF_DYNAMIC_BUNDLE_MANIFEST", None)
            else:
                os.environ["IF_DYNAMIC_BUNDLE_MANIFEST"] = previous_manifest
            if previous_home is None:
                os.environ.pop("HOME", None)
            else:
                os.environ["HOME"] = previous_home


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
