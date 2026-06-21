#!/usr/bin/env python3
"""Unit tests for Hermes gateway E2E CLI runner helpers."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from cli_runner import _redact_env_tail  # noqa: E402


class CliRunnerRedactionTests(unittest.TestCase):
    def test_redact_env_tail_hides_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_file = Path(tmp) / ".env"
            env_file.write_text(
                "API_SERVER_PORT=8642\n"
                "OPENAI_API_KEY=sk-secret-value\n"
                "API_SERVER_KEY=local-key\n",
                encoding="utf-8",
            )
            tail = _redact_env_tail(env_file)
            assert tail is not None
            self.assertIn("API_SERVER_PORT=8642", tail)
            self.assertIn("OPENAI_API_KEY=<redacted>", tail)
            self.assertIn("API_SERVER_KEY=<redacted>", tail)
            self.assertNotIn("sk-secret-value", tail)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
