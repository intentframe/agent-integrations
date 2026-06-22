#!/usr/bin/env python3
"""Contract: gateway E2E probes cover every governed Hermes tool."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_SRC = REPO_ROOT / "integrations" / "hermes" / "shared" / "src"
GATEWAY_DIR = Path(__file__).resolve().parent
TESTS_DIR = REPO_ROOT / "tests"

for path in (SHARED_SRC, GATEWAY_DIR, TESTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from hermes_governance.loader import load_governed_tools  # noqa: E402

import api_client  # noqa: E402
from hermes_tool_probes import GOVERNED_TOOL_NAMES  # noqa: E402


class TestGovernedToolCoverage(unittest.TestCase):
    def test_governance_yaml_matches_probe_registry(self) -> None:
        governed = set(load_governed_tools().keys())
        self.assertEqual(governed, GOVERNED_TOOL_NAMES)
        self.assertEqual(governed, set(api_client.GOVERNED_TOOL_NAMES))

    def test_gateway_e2e_invokes_all_governed_tools(self) -> None:
        source = (GATEWAY_DIR / "test_gateway_e2e.py").read_text(encoding="utf-8")
        for tool in sorted(GOVERNED_TOOL_NAMES):
            if tool == "terminal":
                self.assertIn("run_allow_with_retries", source)
                self.assertIn("run_block_once", source)
            elif tool == "process":
                self.assertIn("run_process_allow_with_retries", source)
                self.assertIn("run_process_block_once", source)
            elif tool == "write_file":
                self.assertIn("run_write_file_allow_with_retries", source)
                self.assertIn("run_write_file_block_once", source)
            elif tool == "delete_file":
                self.assertIn("run_delete_file_allow_with_retries", source)
                self.assertIn("run_delete_file_block_once", source)
            elif tool == "patch":
                self.assertIn("run_patch_replace_allow_with_retries", source)
                self.assertIn("run_patch_replace_block_once", source)
                self.assertIn("run_patch_v4a_mixed_allow_with_retries", source)
                self.assertIn("run_patch_v4a_mixed_block_once", source)

    def test_live_adapter_covers_all_governed_tools(self) -> None:
        source = (TESTS_DIR / "hermes_adapter" / "test_live.py").read_text(encoding="utf-8")
        for tool in GOVERNED_TOOL_NAMES:
            self.assertIn(f'"{tool}"', source, msg=f"missing live adapter probe for {tool}")

    def test_live_plugin_gate_covers_all_governed_tools(self) -> None:
        source = (TESTS_DIR / "hermes_plugin" / "test_bridge_gate_live.py").read_text(encoding="utf-8")
        for tool in GOVERNED_TOOL_NAMES:
            self.assertIn(f'"{tool}"', source, msg=f"missing live plugin gate probe for {tool}")
        self.assertIn("PATCH_V4A_MIXED_ALLOW_ARGS", source)
        self.assertIn("PATCH_V4A_BLOCK_ARGS", source)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
