#!/usr/bin/env python3
"""Write a throwaway governance yaml with every catalog tool IntentFrame-governed.

Used by Hermes live integration tests via HERMES_GOVERNANCE_YAML so catalog-wide
probes run without mutating the default template or runtime user config.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CLI_SRC = REPO_ROOT / "intentframe-integrations-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))

from intentframe_integrations.hermes_governance_contract import (  # noqa: E402
    write_catalog_all_governed_yaml,
)

__all__ = ["write_catalog_all_governed_yaml", "write_catalog_enabled_yaml"]

# Backward-compatible alias.
write_catalog_enabled_yaml = write_catalog_all_governed_yaml


def main() -> int:
    try:
        print(write_catalog_all_governed_yaml())
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
