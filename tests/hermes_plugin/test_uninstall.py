#!/usr/bin/env python3
"""Tests for uninstall hermes."""

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

from intentframe_integrations.hermes_integrate import (  # noqa: E402
    PLUGIN_KEY,
    integrate_hermes,
    is_plugin_enabled,
    is_plugin_installed,
    load_hermes_pack,
)
from intentframe_integrations.hermes_uninstall import (  # noqa: E402
    INSTALLER_RC_MARKER,
    INSTALLER_PATH_LINE,
    remove_installer_shell_path,
    remove_plugin_enabled,
    strip_env_keys,
    uninstall_hermes,
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


class TestUninstallHermes(unittest.TestCase):
    def test_uninstall_removes_all_intentframe_traces(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()

            with patch_home(home):
                pack = load_hermes_pack()
                integrate_hermes(pack, copy=True, sync_adapter=False)

                hermes_env = home / ".hermes" / ".env"
                hermes_env.parent.mkdir(parents=True, exist_ok=True)
                hermes_env.write_text(
                    "OPENAI_API_KEY=sk-test\n"
                    "IF_AGENT_ADAPTER_SOCKET=~/.intentframe/integrations/hermes/adapter.sock\n"
                    "HERMES_GOVERNANCE_YAML=~/.intentframe/integrations/hermes/governance/tools.yaml\n",
                    encoding="utf-8",
                )

                intentframe_home = home / ".intentframe"
                (intentframe_home / "backend").mkdir(parents=True)
                (intentframe_home / "agent-integrations" / "marker").mkdir(parents=True)
                (intentframe_home / "agent-integrations" / "marker" / "x").write_text("x", encoding="utf-8")

                cli_link = home / ".local" / "bin" / "intentframe-integrations"
                cli_link.parent.mkdir(parents=True)
                cli_link.symlink_to("/tmp/fake-cli")

                zshrc = home / ".zshrc"
                zshrc.write_text(
                    "# existing\n"
                    f"{INSTALLER_RC_MARKER}\n"
                    f"{INSTALLER_PATH_LINE}\n",
                    encoding="utf-8",
                )

                self.assertTrue(is_plugin_installed())
                self.assertTrue(is_plugin_enabled())

                result = uninstall_hermes(pack)
                self.assertGreater(len(result.messages), 0)
                self.assertFalse(is_plugin_installed())
                self.assertFalse(is_plugin_enabled())
                self.assertNotIn("IF_AGENT_ADAPTER_SOCKET", hermes_env.read_text(encoding="utf-8"))
                self.assertIn("OPENAI_API_KEY=sk-test", hermes_env.read_text(encoding="utf-8"))
                self.assertFalse(intentframe_home.exists())
                self.assertFalse(cli_link.exists())
                self.assertNotIn(INSTALLER_RC_MARKER, zshrc.read_text(encoding="utf-8"))
                self.assertTrue((home / ".hermes").exists())

    def test_remove_plugin_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text(
                "plugins:\n  enabled:\n    - intentframe-gate\n    - other-plugin\n",
                encoding="utf-8",
            )
            self.assertTrue(remove_plugin_enabled(cfg))
            text = cfg.read_text(encoding="utf-8")
            self.assertNotIn(PLUGIN_KEY, text)
            self.assertIn("other-plugin", text)
            self.assertFalse(remove_plugin_enabled(cfg))

    def test_strip_env_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text(
                "OPENAI_API_KEY=sk-test\n"
                "IF_AGENT_ADAPTER_SOCKET=~/sock\n"
                "# comment\n"
                "KEEP_ME=yes\n",
                encoding="utf-8",
            )
            changed = strip_env_keys(env_path, frozenset({"IF_AGENT_ADAPTER_SOCKET"}))
            self.assertTrue(changed)
            text = env_path.read_text(encoding="utf-8")
            self.assertNotIn("IF_AGENT_ADAPTER_SOCKET", text)
            self.assertIn("OPENAI_API_KEY=sk-test", text)
            self.assertIn("KEEP_ME=yes", text)
            self.assertIn("# comment", text)

    def test_remove_installer_shell_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()
            with patch_home(home):
                zshrc = home / ".zshrc"
                zshrc.write_text(
                    "alias ll='ls -la'\n"
                    "\n"
                    f"{INSTALLER_RC_MARKER}\n"
                    f"{INSTALLER_PATH_LINE}\n",
                    encoding="utf-8",
                )
                changed = remove_installer_shell_path()
                self.assertEqual(changed, [str(zshrc)])
                text = zshrc.read_text(encoding="utf-8")
                self.assertIn("alias ll", text)
                self.assertNotIn(INSTALLER_RC_MARKER, text)

    def test_remove_hermes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()

            with patch_home(home):
                pack = load_hermes_pack()
                integrate_hermes(pack, copy=True, sync_adapter=False)

                hermes_bin = home / ".local" / "bin" / "hermes"
                hermes_bin.parent.mkdir(parents=True)
                hermes_bin.write_text("#!/bin/sh\n", encoding="utf-8")

                uninstall_hermes(pack, remove_hermes=True)

                self.assertFalse((home / ".hermes").exists())
                self.assertFalse((home / ".intentframe").exists())
                self.assertFalse(hermes_bin.exists())


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
