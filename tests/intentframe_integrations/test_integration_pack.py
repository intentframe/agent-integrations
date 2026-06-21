#!/usr/bin/env python3
"""Tests for integration pack parsing."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.integration_pack import load_integration_pack  # noqa: E402


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


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
