#!/usr/bin/env python3
"""Contract: every catalog tool has native gateway E2E probes or live semantic probes."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = Path(__file__).resolve().parent
TESTS_DIR = REPO_ROOT / "tests"

if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from hermes_governance_fixtures import (  # noqa: E402
    GATEWAY_E2E_PROBE_SYMBOLS,
    LIVE_PLUGIN_EXTRA_FIXTURES,
    gateway_e2e_probe_tool_names,
    live_semantic_probe_tool_names,
    template_catalog_tool_names,
    template_generic_mapper_tool_names,
)


class TestGovernedToolCoverage(unittest.TestCase):
    def test_probe_tiers_partition_catalog(self) -> None:
        gateway = gateway_e2e_probe_tool_names()
        live_semantic = live_semantic_probe_tool_names()
        catalog = template_catalog_tool_names()
        self.assertEqual(gateway | live_semantic, catalog)
        self.assertFalse(gateway & live_semantic)
        self.assertEqual(live_semantic, template_generic_mapper_tool_names())

    def test_gateway_probe_registry_covers_native_catalog(self) -> None:
        self.assertEqual(
            frozenset(GATEWAY_E2E_PROBE_SYMBOLS),
            gateway_e2e_probe_tool_names(),
        )
        self.assertFalse(gateway_e2e_probe_tool_names() & live_semantic_probe_tool_names())

    def test_gateway_e2e_invokes_all_native_probed_tools(self) -> None:
        source = (GATEWAY_DIR / "test_gateway_e2e.py").read_text(encoding="utf-8")
        self.assertIn("load_e2e_governance_snapshot", source)
        self.assertIn("snapshot.governed", source)
        for tool, symbols in GATEWAY_E2E_PROBE_SYMBOLS.items():
            self.assertIn(f'"{tool}" in governed', source, msg=f"missing governed guard for {tool!r}")
            for symbol in symbols:
                self.assertIn(
                    symbol,
                    source,
                    msg=f"missing E2E probe {symbol!r} for {tool!r}",
                )

    def test_live_adapter_covers_all_catalog_tools(self) -> None:
        source = (TESTS_DIR / "hermes_adapter" / "test_live.py").read_text(encoding="utf-8")
        for tool in template_catalog_tool_names():
            self.assertIn(f'"{tool}"', source, msg=f"missing live adapter probe for {tool}")

    def test_live_plugin_gate_covers_all_catalog_tools(self) -> None:
        source = (TESTS_DIR / "hermes_plugin" / "test_bridge_gate_live.py").read_text(
            encoding="utf-8"
        )
        for tool in template_catalog_tool_names():
            self.assertIn(f'"{tool}"', source, msg=f"missing live plugin gate probe for {tool}")
        for fixture in LIVE_PLUGIN_EXTRA_FIXTURES:
            self.assertIn(fixture, source)

    def test_toolsets_live_uses_native_gateway_probe_tier_only(self) -> None:
        native = gateway_e2e_probe_tool_names()
        generic = live_semantic_probe_tool_names()
        probe = (GATEWAY_DIR / "probe_hermes_tool_schemas.py").read_text(encoding="utf-8")
        toolsets_live = (GATEWAY_DIR / "test_gateway_toolsets_live.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("gateway_e2e_probe_tool_names", probe)
        self.assertIn("gateway_e2e_probe_tool_names", toolsets_live)
        self.assertNotIn("template_governed_tool_names", toolsets_live)
        for tool in generic:
            self.assertNotIn(
                f'"{tool}"',
                probe,
                msg=f"schema probe must not hardcode generic tool {tool!r}",
            )
        self.assertFalse(native & generic)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
