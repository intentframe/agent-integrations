"""Tests for integration pack install manifest helpers."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intentframe_integrations.pack_install import (
    load_pack_install_manifest,
    pack_install_status_lines,
)


class PackInstallManifestTests(unittest.TestCase):
    def test_status_lines_without_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch(
                "intentframe_integrations.pack_install.pack_install_dir",
                return_value=root,
            ):
                lines = pack_install_status_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("no install manifest", lines[0])

    def test_status_lines_with_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / ".install-manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "ref": "v0.2.0",
                        "installed_at": "2026-06-27T12:00:00Z",
                    }
                ),
                encoding="utf-8",
            )
            with patch(
                "intentframe_integrations.pack_install.pack_install_dir",
                return_value=root,
            ):
                lines = pack_install_status_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("ref v0.2.0", lines[0])
        self.assertIn("installed 2026-06-27T12:00:00Z", lines[0])

    def test_load_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / ".install-manifest.json"
            manifest.write_text('{"ref": "main"}', encoding="utf-8")
            with patch(
                "intentframe_integrations.pack_install.pack_install_manifest_path",
                return_value=manifest,
            ):
                data = load_pack_install_manifest()
        self.assertEqual(data, {"ref": "main"})


if __name__ == "__main__":
    unittest.main()
