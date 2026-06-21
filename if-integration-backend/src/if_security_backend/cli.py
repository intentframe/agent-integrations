"""CLI: if-integration-backend."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from if_security_backend import __version__
from if_security_backend.agent_config import default_test_agent_pack_path, load_agent_pack
from if_security_backend.runtime.paths import executor_log_file, supervisor_log_file
from if_security_backend.runtime.policy import (
    resolve_agent_id,
    resolve_policy_path,
    seed_policy,
)
from if_security_backend.runtime.supervisor import (
    SupervisorError,
    print_status,
    start_supervisor,
    stop_supervisor,
)
def _integration_test_script() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "run_integration_tests.py"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="if-integration-backend",
        description="Generic IntentFrame validate-only backend (runtime + bridge).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_start = sub.add_parser("start", help="Start IntentFrame core, executor, and validate bridge")
    p_start.add_argument("--no-wait", action="store_true")
    p_start.add_argument("--timeout", type=float, default=90.0)
    p_start.add_argument(
        "--agent-config",
        type=Path,
        default=None,
        help="agent.json (or directory of *.json) for bridge auth (default: bundled test agent)",
    )

    sub.add_parser("stop", help="Stop runtime and bridge")
    sub.add_parser("status", help="Runtime and bridge status")

    p_seed = sub.add_parser("seed-policy", help="Seed policy from agent pack or --policy")
    p_seed.add_argument("--policy", type=Path, default=None)
    p_seed.add_argument(
        "--agent-config",
        type=Path,
        default=None,
        help="agent.json (default: bundled config/agents/default/agent.json)",
    )
    p_seed.add_argument("--user-id", default=None)
    p_seed.add_argument("--agent-id", default=None)
    p_seed.add_argument("--skip-if-exists", action="store_true")
    p_seed.add_argument("--no-validate-bundles", action="store_true")

    p_test = sub.add_parser(
        "test",
        help="Backend integration tests (core Actor + bridge HTTP)",
    )
    p_test.add_argument(
        "--agent-config",
        type=Path,
        default=None,
        help="agent.json (default: bundled config/agents/default/agent.json)",
    )

    args = parser.parse_args(argv)

    try:
        match args.command:
            case "start":
                bridge_cfg = args.agent_config or default_test_agent_pack_path()
                pid = start_supervisor(
                    wait=not args.no_wait,
                    timeout=args.timeout,
                    bridge_config=bridge_cfg,
                )
                print(f"Runtime started (wrapper pid {pid})")
                return 0
            case "stop":
                stop_supervisor()
                return 0
            case "status":
                return print_status()
            case "seed-policy":
                agent_cfg = args.agent_config or default_test_agent_pack_path()
                policy_path = resolve_policy_path(args.policy, agent_config=agent_cfg)
                pack = load_agent_pack(agent_cfg)
                user_id = args.user_id or pack.user_id
                agent_id = args.agent_id or resolve_agent_id(None, agent_config=agent_cfg)
                print(f"Policy: {policy_path}")
                print(f"Agent:  {agent_id} user={user_id}")
                seed_policy(
                    yaml_path=policy_path,
                    user_id=user_id,
                    agent_id=agent_id,
                    skip_if_exists=args.skip_if_exists,
                    validate_bundles=not args.no_validate_bundles,
                )
                return 0
            case "test":
                script = _integration_test_script()
                if not script.is_file():
                    print(f"Missing test runner: {script}", file=sys.stderr)
                    return 1
                cmd = [sys.executable, str(script)]
                if args.agent_config:
                    cmd.extend(["--agent-config", str(args.agent_config)])
                return subprocess.call(cmd)
            case _:
                parser.error(f"Unknown command: {args.command}")
                return 2
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        print(f"  Supervisor log: {supervisor_log_file()}", file=sys.stderr)
        print(f"  Executor log:   {executor_log_file()}", file=sys.stderr)
        return 130
    except (SupervisorError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
