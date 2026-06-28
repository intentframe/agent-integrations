"""Tests for read-only control plane models."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from intentframe_control_plane import read_models


class TestReadModels(unittest.TestCase):
    def test_tail_log_lines_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.log"
            self.assertEqual(read_models.tail_log_lines(path, max_lines=5), [])

    def test_tail_log_lines_last_n(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as fh:
            fh.write("\n".join(f"line-{i}" for i in range(10)))
            path = Path(fh.name)
        try:
            lines = read_models.tail_log_lines(path, max_lines=3)
            self.assertEqual(lines, ["line-7", "line-8", "line-9"])
        finally:
            path.unlink(missing_ok=True)

    def test_load_governance_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            gov = Path(tmp) / "governance" / "tools.yaml"
            gov.parent.mkdir(parents=True)
            gov.write_text(
                "tools:\n"
                "  shell:\n"
                "    enabled: false\n"
                "  read:\n"
                "    enabled: true\n",
                encoding="utf-8",
            )
            with patch.object(read_models, "GOVERNANCE_YAML", gov):
                data = read_models.load_governance_dict()
            self.assertEqual(data["agent"], "hermes")
            self.assertEqual(data["runtime_governed"], ["read"])
            names = [tool["name"] for tool in data["tools"]]
            self.assertEqual(names, ["read", "shell"])


if __name__ == "__main__":
    unittest.main()
