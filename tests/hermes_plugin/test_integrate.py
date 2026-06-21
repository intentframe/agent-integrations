#!/usr/bin/env python3
"""Tests for integrate hermes (uses temp HOME)."""

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
    merge_plugin_enabled,
    plugin_install_path,
)


class TestIntegrateHermes(unittest.TestCase):
    def test_symlink_install_and_config_merge(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()

            with patch_home(home):
                pack = load_hermes_pack()
                result = integrate_hermes(pack, sync_adapter=False)

                self.assertTrue(result.plugin_installed)
                self.assertTrue(is_plugin_installed())
                dest = plugin_install_path()
                self.assertTrue(dest.is_symlink())
                self.assertTrue(is_plugin_enabled(home / ".hermes" / "config.yaml"))
                self.assertIn(PLUGIN_KEY, str(result.messages))

    def test_merge_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            self.assertTrue(merge_plugin_enabled(cfg))
            self.assertFalse(merge_plugin_enabled(cfg))
            self.assertTrue(is_plugin_enabled(cfg))

    def test_merge_preserves_existing_config_comments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg = Path(tmp) / "config.yaml"
            cfg.write_text(
                "# user comment\n"
                "model:\n"
                "  provider: openai-api\n"
                "plugins:\n"
                "  enabled:\n"
                "    - other-plugin\n",
                encoding="utf-8",
            )
            self.assertTrue(merge_plugin_enabled(cfg))
            text = cfg.read_text(encoding="utf-8")
            self.assertIn("# user comment", text)
            self.assertIn("provider: openai-api", text)
            self.assertIn("- other-plugin", text)
            self.assertIn(f"- {PLUGIN_KEY}", text)
            self.assertTrue((cfg.with_name("config.yaml.intentframe.bak")).is_file())

    def test_copy_install_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "home"
            home.mkdir()

            with patch_home(home):
                pack = load_hermes_pack()
                integrate_hermes(pack, copy=True, sync_adapter=False)
                integrate_hermes(pack, copy=True, sync_adapter=False)
                dest = plugin_install_path()
                self.assertTrue(dest.is_dir())
                self.assertTrue((dest / "plugin.yaml").is_file())


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


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
