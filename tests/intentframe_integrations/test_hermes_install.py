#!/usr/bin/env python3
"""Tests for Hermes install, resolver, doctor stages, and gateway config."""

from __future__ import annotations

import json
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

from intentframe_integrations.hermes_gateway import (  # noqa: E402
    ensure_api_server_config,
    gateway_pid_file,
)
from intentframe_integrations.hermes_install import (  # noqa: E402
    DEFAULT_HERMES_AGENT_VERSION,
    HermesInstallError,
    install_record_path,
    install_hermes_agent,
    is_managed_hermes_installed,
    managed_hermes_bin,
    resolve_hermes_bin,
)
from intentframe_integrations.hermes_integrate import (  # noqa: E402
    doctor_hermes,
    integrate_hermes,
    is_plugin_enabled,
    load_hermes_pack,
)
from intentframe_integrations.hermes_paths import hermes_home  # noqa: E402


class patch_home:
    def __init__(self, home: Path, *, hermes_home: Path | None = None) -> None:
        self.home = home
        self.hermes_home = hermes_home
        self._previous_home: str | None = None
        self._previous_hermes_home: str | None = None

    def __enter__(self) -> None:
        self._previous_home = os.environ.get("HOME")
        self._previous_hermes_home = os.environ.get("HERMES_HOME")
        os.environ["HOME"] = str(self.home)
        if self.hermes_home is not None:
            os.environ["HERMES_HOME"] = str(self.hermes_home)
        elif "HERMES_HOME" in os.environ:
            os.environ.pop("HERMES_HOME")
        return None

    def __exit__(self, *args: object) -> None:
        if self._previous_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = self._previous_home
        if self._previous_hermes_home is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._previous_hermes_home


class TestHermesResolver(unittest.TestCase):
    def test_resolve_prefers_hermes_bin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            binary = Path(tmp) / "hermes"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)
            with patch.dict(os.environ, {"HERMES_BIN": str(binary)}, clear=False):
                self.assertEqual(resolve_hermes_bin(), binary)

    def test_resolve_managed_before_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            managed = home / ".intentframe" / "integrations" / "hermes" / "hermes-agent-venv" / "bin"
            managed.mkdir(parents=True)
            binary = managed / "hermes"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)

            with patch_home(home):
                with patch.dict(os.environ, {}, clear=True):
                    os.environ["HOME"] = str(home)
                    resolved = resolve_hermes_bin()
                    self.assertEqual(resolved, binary)


class TestHermesInstall(unittest.TestCase):
    def test_install_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            hermes_data = Path(tmp) / "hermes-home"
            home.mkdir()
            hermes_data.mkdir()

            def fake_check_call(cmd: list[str]) -> None:
                if cmd[:3] == ["uv", "venv"]:
                    venv = Path(cmd[2])
                    (venv / "bin").mkdir(parents=True, exist_ok=True)
                    py = venv / "bin" / "python"
                    py.write_text("", encoding="utf-8")
                if cmd[:3] == ["uv", "pip", "install"]:
                    binary = managed_hermes_bin()
                    binary.parent.mkdir(parents=True, exist_ok=True)
                    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
                    binary.chmod(0o755)

            with patch_home(home, hermes_home=hermes_data):
                with patch("intentframe_integrations.hermes_install.subprocess.check_call", side_effect=fake_check_call):
                    first = install_hermes_agent()
                    second = install_hermes_agent()

                self.assertFalse(first.already_installed)
                self.assertTrue(second.already_installed)
                self.assertTrue(is_managed_hermes_installed(version=DEFAULT_HERMES_AGENT_VERSION))
                record = json.loads(install_record_path().read_text(encoding="utf-8"))
                self.assertEqual(record["version"], DEFAULT_HERMES_AGENT_VERSION)

    def test_install_fails_when_binary_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()

            def fake_check_call(cmd: list[str]) -> None:
                if cmd[:3] == ["uv", "venv"]:
                    venv = Path(cmd[2])
                    (venv / "bin").mkdir(parents=True, exist_ok=True)

            with patch_home(home):
                with patch("intentframe_integrations.hermes_install.subprocess.check_call", side_effect=fake_check_call):
                    with self.assertRaises(HermesInstallError):
                        install_hermes_agent()


class TestDoctorStages(unittest.TestCase):
    def test_install_only_doctor_fails_without_hermes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            with patch_home(home):
                pack = load_hermes_pack()
                report = doctor_hermes(pack, require_hermes=True, require_integration=False)
                self.assertFalse(report.ok)
                self.assertIn("hermes CLI: not found", "\n".join(report.lines))

    def test_full_doctor_fails_before_integrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            hermes_data = Path(tmp) / "hermes-home"
            home.mkdir()
            managed = home / ".intentframe" / "integrations" / "hermes" / "hermes-agent-venv" / "bin"
            managed.mkdir(parents=True)
            binary = managed / "hermes"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)

            with patch_home(home, hermes_home=hermes_data):
                pack = load_hermes_pack()
                _apply_env(pack)
                report = doctor_hermes(pack)
                self.assertFalse(report.ok)
                joined = "\n".join(report.lines)
                self.assertIn("plugin install: missing", joined)

    def test_full_doctor_passes_after_integrate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            hermes_data = Path(tmp) / "hermes-home"
            home.mkdir()
            managed = home / ".intentframe" / "integrations" / "hermes" / "hermes-agent-venv" / "bin"
            managed.mkdir(parents=True)
            binary = managed / "hermes"
            binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            binary.chmod(0o755)

            with patch_home(home, hermes_home=hermes_data):
                pack = load_hermes_pack()
                _apply_env(pack)
                integrate_hermes(pack, sync_adapter=False)
                bridge = home / ".intentframe" / "backend" / "bridge.sock"
                bridge.parent.mkdir(parents=True, exist_ok=True)
                bridge.write_text("", encoding="utf-8")
                venv_py = home / ".intentframe" / "integrations" / "hermes" / ".venv" / "bin" / "python"
                venv_py.parent.mkdir(parents=True, exist_ok=True)
                venv_py.write_text("", encoding="utf-8")
                with patch("if_security_backend.runtime.paths.bridge_socket_path", return_value=bridge):
                    with patch("intentframe_integrations.hermes_integrate.is_adapter_running", return_value=True):
                        with patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
                            report = doctor_hermes(pack)
                self.assertTrue(report.ok)


class TestGatewayConfig(unittest.TestCase):
    def test_api_server_env_written_to_hermes_home(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes_data = Path(tmp) / "hermes-home"
            with patch.dict(os.environ, {"HERMES_HOME": str(hermes_data)}, clear=False):
                cfg = ensure_api_server_config(api_key="test-key", port=18642, host="127.0.0.1")
                env_path = hermes_home() / ".env"
                self.assertTrue(env_path.is_file())
                self.assertEqual(cfg["API_SERVER_ENABLED"], "true")
                self.assertEqual(cfg["API_SERVER_KEY"], "test-key")
                self.assertIn("API_SERVER_ENABLED=true", env_path.read_text(encoding="utf-8"))

    def test_gateway_pid_file_under_integration_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            with patch_home(home):
                self.assertEqual(
                    gateway_pid_file(),
                    home / ".intentframe" / "integrations" / "hermes" / "gateway.pid",
                )


def _apply_env(pack: object) -> None:
    from intentframe_integrations.cli import _apply_agent_env

    _apply_agent_env(pack)  # type: ignore[arg-type]


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
