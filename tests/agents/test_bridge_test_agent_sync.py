#!/usr/bin/env python3
"""Ensure e2e bridge_test agent pack stays aligned with bundled default."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
E2E_AGENT = REPO_ROOT / "tests" / "agents" / "bridge-test" / "agent.json"
E2E_POLICY = REPO_ROOT / "tests" / "agents" / "bridge-test" / "policy.yaml"
BUNDLED_AGENT = (
    REPO_ROOT
    / "if-integration-backend"
    / "src"
    / "if_security_backend"
    / "config"
    / "agents"
    / "default"
    / "agent.json"
)
BUNDLED_POLICY = BUNDLED_AGENT.parent / "policy.yaml"


class TestBridgeTestAgentSync(unittest.TestCase):
    def test_agent_json_matches_bundled_default(self) -> None:
        e2e = json.loads(E2E_AGENT.read_text(encoding="utf-8"))
        bundled = json.loads(BUNDLED_AGENT.read_text(encoding="utf-8"))
        for key in (
            "agent_id",
            "user_id",
            "agent_type",
            "action_types",
            "bridge_secret",
            "policy_file",
        ):
            self.assertEqual(e2e.get(key), bundled.get(key), msg=f"mismatch on {key!r}")

    def test_policy_allowed_actions_match_bundled_default(self) -> None:
        e2e = yaml.safe_load(E2E_POLICY.read_text(encoding="utf-8"))
        bundled = yaml.safe_load(BUNDLED_POLICY.read_text(encoding="utf-8"))
        self.assertEqual(e2e.get("allowed_actions"), bundled.get("allowed_actions"))
        self.assertEqual(e2e.get("domain_constraints"), bundled.get("domain_constraints"))


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
