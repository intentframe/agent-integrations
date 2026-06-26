#!/usr/bin/env python3
"""Tests for adapter sidecar lifecycle helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.adapter_lifecycle import (  # noqa: E402
    AdapterError,
    adapter_importable,
    adapter_python,
    adapter_top_package,
    ensure_adapter_importable,
)
from intentframe_integrations.integration_pack import load_integration_pack  # noqa: E402


class TestAdapterLifecycle(unittest.TestCase):
    def test_adapter_top_package(self) -> None:
        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        self.assertEqual(adapter_top_package(pack), "hermes_adapter")

    def test_adapter_python_is_current_interpreter(self) -> None:
        self.assertEqual(adapter_python(), Path(sys.executable))

    def test_ensure_importable_raises_when_missing(self) -> None:
        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        with patch(
            "intentframe_integrations.adapter_lifecycle.importlib.util.find_spec",
            return_value=None,
        ):
            self.assertFalse(adapter_importable(pack))
            with self.assertRaises(AdapterError):
                ensure_adapter_importable(pack)


class TestAdapterImportableReal(unittest.TestCase):
    """The adapter package is importable in the workspace interpreter."""

    def test_adapter_importable_in_workspace_venv(self) -> None:
        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        self.assertTrue(adapter_importable(pack))
        ensure_adapter_importable(pack)

        proc = __import__("subprocess").run(
            [str(adapter_python()), "-c", "import hermes_adapter; print('ok')"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "ok")


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
