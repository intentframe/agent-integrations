#!/usr/bin/env python3
"""Contract checks against local Hermes source reference (external-reference-only-libs)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
HERMES_REF = REPO_ROOT / "external-reference-only-libs" / "hermes-agent"
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.hermes_gateway import (  # noqa: E402
    DEFAULT_API_HOST,
    DEFAULT_API_PORT,
    DEFAULT_HERMES_GATEWAY_COMMAND,
    HERMES_GATEWAY_RUN_FLAGS,
    HERMES_GATEWAY_SERVICE_SUBCOMMANDS,
    normalize_hermes_gateway_argv,
)


def _require_reference() -> None:
    if not HERMES_REF.is_dir():
        raise unittest.SkipTest(
            f"Hermes reference not present at {HERMES_REF} — clone/update external-reference-only-libs"
        )


class HermesReferenceContractTests(unittest.TestCase):
    def test_gateway_run_is_foreground_subcommand(self) -> None:
        _require_reference()
        text = (HERMES_REF / "hermes_cli" / "subcommands" / "gateway.py").read_text(encoding="utf-8")
        self.assertIn('"run", help="Run gateway in foreground', text)
        self.assertIn('"start", help="Start the installed systemd/launchd background service"', text)

    def test_api_server_env_keys_in_reference_config(self) -> None:
        _require_reference()
        text = (HERMES_REF / "hermes_cli" / "config.py").read_text(encoding="utf-8")
        for key in ("API_SERVER_ENABLED", "API_SERVER_KEY", "API_SERVER_PORT", "API_SERVER_HOST"):
            self.assertIn(f'"{key}"', text)

    def test_api_endpoints_in_reference_server(self) -> None:
        _require_reference()
        text = (HERMES_REF / "gateway" / "platforms" / "api_server.py").read_text(encoding="utf-8")
        for route in ("/health", "/v1/capabilities", "/v1/responses", "/v1/toolsets"):
            self.assertIn(route, text)

    def test_openai_api_provider_in_reference_auth(self) -> None:
        _require_reference()
        text = (HERMES_REF / "hermes_cli" / "auth.py").read_text(encoding="utf-8")
        self.assertIn("openai-api", text)
        self.assertIn("OPENAI_API_KEY", text)

    def test_orchestrator_defaults_match_reference(self) -> None:
        _require_reference()
        config_text = (HERMES_REF / "hermes_cli" / "config.py").read_text(encoding="utf-8")
        self.assertIn("API_SERVER_PORT", config_text)
        self.assertIn("default: 8642", config_text)
        self.assertEqual(DEFAULT_API_HOST, "127.0.0.1")
        self.assertEqual(DEFAULT_HERMES_GATEWAY_COMMAND, "run")

    def test_run_flags_present_in_reference_parser(self) -> None:
        _require_reference()
        gateway_text = (HERMES_REF / "hermes_cli" / "subcommands" / "gateway.py").read_text(
            encoding="utf-8"
        )
        shared_text = (HERMES_REF / "hermes_cli" / "subcommands" / "_shared.py").read_text(
            encoding="utf-8"
        )
        for flag in ("--replace", "--verbose"):
            self.assertIn(flag, gateway_text)
        self.assertIn("--accept-hooks", shared_text)

    def test_normalize_never_passes_service_subcommands(self) -> None:
        for subcmd in HERMES_GATEWAY_SERVICE_SUBCOMMANDS:
            argv = normalize_hermes_gateway_argv([subcmd, "--replace"])
            self.assertEqual(argv[0], DEFAULT_HERMES_GATEWAY_COMMAND)
            self.assertNotIn(subcmd, argv)
        for flag in HERMES_GATEWAY_RUN_FLAGS:
            if flag.startswith("-"):
                argv = normalize_hermes_gateway_argv([flag])
                self.assertIn(flag, argv)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
