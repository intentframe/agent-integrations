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

from intentframe_integrations.adapter_lifecycle import _adapter_package_name  # noqa: E402
from intentframe_integrations.integration_pack import load_integration_pack  # noqa: E402


class TestAdapterLifecycle(unittest.TestCase):
    def test_adapter_package_name(self) -> None:
        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        self.assertEqual(_adapter_package_name(pack), "hermes-adapter")

    @patch("intentframe_integrations.adapter_lifecycle.subprocess.check_call")
    @patch("intentframe_integrations.adapter_lifecycle.adapter_venv_python")
    def test_sync_exports_and_installs(self, venv_py: object, check_call: object) -> None:
        from unittest.mock import MagicMock

        from intentframe_integrations.adapter_lifecycle import sync_adapter_venv

        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        fake_python = MagicMock()
        fake_python.is_file.return_value = True
        fake_python.__str__ = lambda _self: "/tmp/fake-venv/bin/python"  # type: ignore[method-assign]
        venv_py.return_value = fake_python

        sync_adapter_venv(pack)

        self.assertEqual(check_call.call_count, 2)
        export_cmd = check_call.call_args_list[0].args[0]
        install_cmd = check_call.call_args_list[1].args[0]
        self.assertEqual(export_cmd[1], "export")
        self.assertIn("hermes-adapter", export_cmd)
        self.assertIn("-q", export_cmd)
        self.assertEqual(install_cmd[1], "pip")
        self.assertEqual(install_cmd[2], "install")
        self.assertIn("-q", install_cmd)


class TestAdapterVenvSyncReal(unittest.TestCase):
    """Real uv export+pip into a temp adapter state dir (not mocked)."""

    def test_sync_creates_runnable_venv(self) -> None:
        import os
        import tempfile

        from intentframe_integrations.adapter_lifecycle import (
            adapter_venv_python,
            integration_state_dir,
            sync_adapter_venv,
        )

        pack = load_integration_pack(REPO_ROOT / "integrations/hermes/agent.json")
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            previous = os.environ.get("HOME")
            os.environ["HOME"] = str(home)
            try:
                sync_adapter_venv(pack)
                venv_py = adapter_venv_python("hermes")
                state = integration_state_dir("hermes")
            finally:
                if previous is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = previous

            self.assertTrue(venv_py.is_file())
            self.assertTrue((state / "adapter-requirements.txt").is_file())

            proc = __import__("subprocess").run(
                [str(venv_py), "-c", "import hermes_adapter; print('ok')"],
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
