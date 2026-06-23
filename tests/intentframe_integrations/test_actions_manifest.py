#!/usr/bin/env python3
"""Dev golden test: committed generic_actions.manifest and derived configs match the catalog.

These artifacts are dev-generated and static; they only change when a developer
adds a tool to governance/tools.yaml. This test fails on drift so they cannot
silently diverge — nothing regenerates them at runtime.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.hermes_governance_contract import (  # noqa: E402
    catalog_generic_action_ids,
    default_actions_manifest_template_path,
    format_manifest,
)


def _catalog_all_action_ids() -> frozenset[str]:
    template = REPO_ROOT / "integrations" / "hermes" / "governance" / "tools.yaml"
    raw = yaml.safe_load(template.read_text(encoding="utf-8")) or {}
    actions: set[str] = set()
    for spec in raw.get("tools", {}).values():
        if not isinstance(spec, dict):
            continue
        action = str(spec.get("action", "")).strip()
        if action:
            actions.add(action)
        for extra in spec.get("actions", []) or []:
            if str(extra).strip():
                actions.add(str(extra).strip())
    return frozenset(actions)


class TestActionsManifestGolden(unittest.TestCase):
    def test_committed_manifest_matches_full_generic_catalog(self) -> None:
        manifest = default_actions_manifest_template_path()
        self.assertTrue(manifest.is_file(), f"missing committed manifest: {manifest}")
        present = {
            part.strip()
            for part in manifest.read_text(encoding="utf-8").split(",")
            if part.strip()
        }
        self.assertEqual(
            present,
            set(catalog_generic_action_ids()),
            "committed generic_actions.manifest is out of sync with the generic catalog; "
            f"regenerate it to: {format_manifest(catalog_generic_action_ids())}",
        )

    def test_agent_json_action_types_cover_catalog(self) -> None:
        agent_path = REPO_ROOT / "integrations" / "hermes" / "agent.json"
        raw = json.loads(agent_path.read_text(encoding="utf-8"))
        action_types = set(raw.get("action_types", []))
        missing = sorted(_catalog_all_action_ids() - action_types)
        self.assertEqual([], missing, f"agent.json action_types missing: {missing}")

    def test_executor_supported_actions_cover_catalog(self) -> None:
        executor_path = (
            REPO_ROOT
            / "if-integration-backend"
            / "src"
            / "if_security_backend"
            / "config"
            / "profiles"
            / "executor.yaml"
        )
        raw = yaml.safe_load(executor_path.read_text(encoding="utf-8")) or {}
        supported = set(
            raw.get("pack_options", {}).get("validate_only", {}).get("supported_actions", [])
        )
        missing = sorted(_catalog_all_action_ids() - supported)
        self.assertEqual([], missing, f"executor supported_actions missing: {missing}")


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
