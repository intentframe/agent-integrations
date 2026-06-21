#!/usr/bin/env python3
"""Unit tests for Hermes gateway E2E isolation helpers."""

from __future__ import annotations

import os
import sys
import unittest
import unittest.mock
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from isolation import (  # noqa: E402
    HERMES_E2E_DEFAULT_MODEL,
    HERMES_E2E_OPENAI_PROVIDER,
    _MAX_UDS_PATH_LEN,
    _assert_uds_paths_fit,
    _longest_uds_path,
    activate,
    assert_hermes_openai_seeded,
    cleanup_tree,
    create_isolated_env,
    deactivate,
    sandbox_backend_uds_paths,
    seed_hermes_openai_for_e2e,
)


class IsolationUdsPathTests(unittest.TestCase):
    def test_create_isolated_env_uds_paths_within_limit(self) -> None:
        env = create_isolated_env()
        try:
            for path in sandbox_backend_uds_paths(env.home):
                with self.subTest(path=str(path)):
                    self.assertLess(
                        len(str(path)),
                        _MAX_UDS_PATH_LEN,
                        msg=f"UDS path exceeds macOS AF_UNIX limit: {path}",
                    )
        finally:
            cleanup_tree(env)

    def test_assert_uds_paths_fit_rejects_long_home(self) -> None:
        if os.name == "nt":
            self.skipTest("AF_UNIX path length check is Unix-only")
        long_home = Path("/var/folders/wl/7lwf1tdn5f13s4pcs45n65n80000gn/T") / (
            "hermes-gateway-e2e." + ("x" * 24)
        )
        with self.assertRaisesRegex(RuntimeError, "UDS path too long"):
            _assert_uds_paths_fit(long_home / "home")

    def test_sandbox_home_is_short_on_unix(self) -> None:
        if os.name == "nt":
            self.skipTest("Short /tmp sandbox layout is Unix-only")
        env = create_isolated_env()
        try:
            self.assertEqual(env.home, env.test_root)
            self.assertTrue(str(env.home).startswith("/tmp/hg"))
            self.assertEqual(env.hermes_home, env.test_root / "hh")
            longest = _longest_uds_path(env.home)
            self.assertLess(len(str(longest)), _MAX_UDS_PATH_LEN)
        finally:
            cleanup_tree(env)


class HermesOpenAiSeedTests(unittest.TestCase):
    def test_seed_hermes_openai_for_e2e_writes_sandbox_config(self) -> None:
        env = create_isolated_env()
        try:
            with self.subTest(step="activate+seed"):
                with unittest.mock.patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-seed"}, clear=False):
                    activate(env)
                    seed_hermes_openai_for_e2e(env)
                    assert_hermes_openai_seeded(env)

            raw = yaml.safe_load(env.hermes_config_path.read_text(encoding="utf-8"))
            self.assertIsInstance(raw, dict)
            model = raw["model"]
            self.assertEqual(model["provider"], HERMES_E2E_OPENAI_PROVIDER)
            self.assertEqual(model["default"], HERMES_E2E_DEFAULT_MODEL)
            self.assertEqual(raw["plugins"]["enabled"], [])

            env_text = env.hermes_env_file.read_text(encoding="utf-8")
            self.assertIn("OPENAI_API_KEY=sk-test-seed", env_text)
        finally:
            deactivate(env)
            cleanup_tree(env)

    def test_seed_requires_openai_api_key(self) -> None:
        env = create_isolated_env()
        try:
            without_key = {k: v for k, v in os.environ.items() if k != "OPENAI_API_KEY"}
            with unittest.mock.patch.dict(os.environ, without_key, clear=True):
                with self.assertRaisesRegex(RuntimeError, "OPENAI_API_KEY"):
                    seed_hermes_openai_for_e2e(env)
        finally:
            cleanup_tree(env)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
