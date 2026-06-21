#!/usr/bin/env python3
"""Backend integration tests: core Actor connection + bridge HTTP."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from integration.bridge_connection import run_bridge_connection_tests
from integration.core_connection import run_core_connection_tests


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="if-integration-backend integration tests")
    parser.add_argument(
        "--agent-config",
        type=Path,
        default=None,
        help="agent.json (default: bundled config/agents/default/agent.json)",
    )
    args = parser.parse_args(argv)

    print("==> Core connection (Actor → IntentFrame)")
    ec = run_core_connection_tests(args.agent_config)
    if ec:
        return ec

    print("\n==> Bridge connection (HTTP → bridge.sock)")
    return run_bridge_connection_tests(args.agent_config)


if __name__ == "__main__":
    raise SystemExit(main())
