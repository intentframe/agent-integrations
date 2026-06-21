"""intentframe-integrations — user-facing orchestrator for agent profiles."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from if_security_backend.agent_config import load_agent_pack
from if_security_backend.cli import main as backend_main

from intentframe_integrations.__version__ import __version__
from intentframe_integrations.paths import agent_config_path, list_agents


def _apply_agent_env(agent_config: Path) -> None:
    pack = load_agent_pack(agent_config)
    os.environ.setdefault("INTENTFRAME_USER_ID", pack.user_id)
    os.environ.setdefault("INTENTFRAME_AGENT_ID", pack.agent_id)


def _run_backend(argv: list[str]) -> int:
    return backend_main(argv)


def _require_openai_api_key() -> int | None:
    if os.environ.get("OPENAI_API_KEY"):
        return None
    print(
        "ERROR: OPENAI_API_KEY is not set (required for IntentFrame core).",
        file=sys.stderr,
    )
    return 1


def _seed_agent_config(cfg: Path, *, skip_if_exists: bool) -> int:
    if cfg.is_file():
        _apply_agent_env(cfg)
        paths = [cfg]
    elif cfg.is_dir():
        paths = sorted(cfg.rglob("agent.json"))
        if not paths:
            print(f"ERROR: no agent.json files under {cfg}", file=sys.stderr)
            return 1
    else:
        print(f"ERROR: agent config not found: {cfg}", file=sys.stderr)
        return 1

    for path in paths:
        argv = ["seed-policy", "--agent-config", str(path)]
        if skip_if_exists:
            argv.append("--skip-if-exists")
        ec = _run_backend(argv)
        if ec:
            return ec
    return 0


def _cmd_start(agent: str, *, seed: bool, skip_if_exists: bool) -> int:
    if (ec := _require_openai_api_key()) is not None:
        return ec

    cfg = agent_config_path(agent)
    _apply_agent_env(cfg)

    ec = _run_backend(["start", "--agent-config", str(cfg)])
    if ec:
        return ec

    if seed:
        ec = _seed_agent_config(cfg, skip_if_exists=skip_if_exists)
        if ec:
            return ec

    print(
        f"\nIntentFrame Integrations runtime is up for agent {agent!r}.\n"
        "Bridge: ~/.intentframe/backend/bridge.sock\n"
        "If Hermes is already installed, export env from integrations/hermes/agent.json "
        "and restart your Hermes gateway so the IntentFrame plugin can connect."
    )
    return 0


def _cmd_start_config(
    agent_config: Path,
    *,
    seed: bool,
    skip_if_exists: bool,
) -> int:
    if (ec := _require_openai_api_key()) is not None:
        return ec

    cfg = agent_config.expanduser().resolve()
    if cfg.is_file():
        _apply_agent_env(cfg)
    elif not cfg.is_dir():
        print(f"ERROR: agent config not found: {cfg}", file=sys.stderr)
        return 1

    ec = _run_backend(["start", "--agent-config", str(cfg)])
    if ec:
        return ec

    if seed:
        ec = _seed_agent_config(cfg, skip_if_exists=skip_if_exists)
        if ec:
            return ec

    print(
        f"\nIntentFrame Integrations runtime is up ({cfg}).\n"
        "Bridge: ~/.intentframe/backend/bridge.sock"
    )
    return 0


def _cmd_seed(agent: str, *, skip_if_exists: bool) -> int:
    cfg = agent_config_path(agent)
    return _seed_agent_config(cfg, skip_if_exists=skip_if_exists)


def _cmd_seed_config(agent_config: Path, *, skip_if_exists: bool) -> int:
    cfg = agent_config.expanduser().resolve()
    return _seed_agent_config(cfg, skip_if_exists=skip_if_exists)


def _cmd_test(agent_config: Path | None) -> int:
    argv = ["test"]
    if agent_config is not None:
        argv.extend(["--agent-config", str(agent_config.expanduser().resolve())])
    return _run_backend(argv)


def _cmd_doctor(agent: str) -> int:
    cfg = agent_config_path(agent)
    pack = load_agent_pack(cfg)
    bridge_socket = Path(os.path.expanduser("~/.intentframe/backend/bridge.sock"))

    print(f"Repo agent config: {cfg}")
    print(f"  agent_id:  {pack.agent_id}")
    print(f"  user_id:   {pack.user_id}")
    print(f"  bridge:    {pack.env.get('IF_SECURITY_BRIDGE_SOCKET', '~/.intentframe/backend/bridge.sock')}")

    if os.environ.get("OPENAI_API_KEY"):
        print("  OPENAI_API_KEY: set")
    else:
        print("  OPENAI_API_KEY: MISSING", file=sys.stderr)
        return 1

    if bridge_socket.exists():
        print(f"  bridge socket: present ({bridge_socket})")
    else:
        print(f"  bridge socket: not found ({bridge_socket}) — run: intentframe-integrations start {agent}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="intentframe-integrations",
        description=(
            "IntentFrame Integrations — start the validate bridge/runtime for external agents "
            "(Hermes, OpenClaw, …). Does not replace upstream intentframe or intentframe-gateway-cli."
        ),
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    agents = list_agents()

    p_start = sub.add_parser(
        "start",
        help="Start validate runtime + bridge for an agent profile",
    )
    p_start.add_argument(
        "agent",
        nargs="?",
        choices=agents,
        help="Integration profile (e.g. hermes)",
    )
    p_start.add_argument(
        "--agent-config",
        type=Path,
        default=None,
        help="agent.json or directory of agents (e2e/dev; bypasses named profile)",
    )
    p_start.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seed-policy after start",
    )
    p_start.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Pass --skip-if-exists to seed-policy",
    )

    sub.add_parser("stop", help="Stop IntentFrame runtime and bridge")
    sub.add_parser("status", help="Runtime and bridge status")

    p_seed = sub.add_parser("seed", help="Seed policy for an agent profile")
    p_seed.add_argument("agent", nargs="?", choices=agents)
    p_seed.add_argument(
        "--agent-config",
        type=Path,
        default=None,
        help="agent.json or directory of agents (e2e/dev)",
    )
    p_seed.add_argument("--skip-if-exists", action="store_true")

    p_test = sub.add_parser(
        "test",
        help="Backend integration tests (core Actor + bridge HTTP)",
    )
    p_test.add_argument(
        "--agent-config",
        type=Path,
        default=None,
        help="agent.json (default: bundled test agent)",
    )

    p_doctor = sub.add_parser("doctor", help="Check agent config and runtime prerequisites")
    p_doctor.add_argument("agent", choices=agents)

    args = parser.parse_args(argv)

    match args.command:
        case "start":
            if args.agent_config is not None:
                if args.agent is not None:
                    parser.error("use either agent name or --agent-config, not both")
                return _cmd_start_config(
                    args.agent_config,
                    seed=not args.no_seed,
                    skip_if_exists=args.skip_if_exists,
                )
            if args.agent is None:
                parser.error("agent name or --agent-config is required")
            return _cmd_start(
                args.agent,
                seed=not args.no_seed,
                skip_if_exists=args.skip_if_exists,
            )
        case "stop":
            return _run_backend(["stop"])
        case "status":
            return _run_backend(["status"])
        case "seed":
            if args.agent_config is not None:
                if args.agent is not None:
                    parser.error("use either agent name or --agent-config, not both")
                return _cmd_seed_config(args.agent_config, skip_if_exists=args.skip_if_exists)
            if args.agent is None:
                parser.error("agent name or --agent-config is required")
            return _cmd_seed(args.agent, skip_if_exists=args.skip_if_exists)
        case "test":
            return _cmd_test(args.agent_config)
        case "doctor":
            return _cmd_doctor(args.agent)
        case _:
            parser.error(f"Unknown command: {args.command}")
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
