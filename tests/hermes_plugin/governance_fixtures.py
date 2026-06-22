"""HERMES_GOVERNANCE_YAML setup for plugin unit tests (no runtime seed required)."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from hermes_governance_fixtures import PluginGovernanceEnvMixin  # noqa: E402

__all__ = ["PluginGovernanceEnvMixin"]
