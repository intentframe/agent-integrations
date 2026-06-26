"""intentframe-integrations — user-facing orchestrator for agent profiles.

Commands that need agent env or Hermes runtime artifacts use
``load_and_activate_pack*`` from ``integration_pack`` (not raw ``load_integration_pack``).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

from if_security_backend.cli import main as backend_main

from intentframe_integrations.__version__ import __version__
from intentframe_integrations.adapter_lifecycle import (
    AdapterError,
    adapter_status_line,
    is_adapter_running,
    start_adapter,
    stop_adapter,
)
from intentframe_integrations.hermes_gateway import (
    HermesGatewayError,
    gateway_log_file,
    is_gateway_running,
    start_hermes_gateway,
    stop_hermes_gateway,
)
from intentframe_integrations.hermes_install import (
    HermesInstallError,
    install_hermes_agent,
    resolve_hermes_bin,
)
from intentframe_integrations.hermes_integrate import (
    doctor_hermes,
    format_env_exports,
    integrate_hermes,
)
from intentframe_integrations.hermes_governance_edit import (
    GovernanceEditError,
    list_governed_tools,
    runtime_governed_tool_names,
    set_tool_enabled,
)
from intentframe_integrations.integration_pack import (
    IntegrationPack,
    load_and_activate_pack,
    load_and_activate_pack_from_path,
    load_integration_pack,
)
from intentframe_integrations.policy_contract import ensure_runtime_policy_yaml
from intentframe_integrations.policy_manage import (
    PolicyError,
    format_policy_show,
    policy_reload,
    policy_reset,
    policy_set,
    policy_show,
)
from intentframe_integrations.paths import agent_config_path, list_agents
from intentframe_integrations.runtime_lifecycle import (
    backend_ready_for_pack,
    ensure_backend_for_pack,
    iter_agent_configs,
)


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
        # Seed policy path + agent env before delegating to backend seed-policy.
        pack = load_and_activate_pack_from_path(path)
        try:
            runtime_policy = ensure_runtime_policy_yaml(pack)
        except FileNotFoundError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

        argv = [
            "seed-policy",
            "--agent-config",
            str(path),
            "--policy",
            str(runtime_policy),
        ]
        if skip_if_exists:
            argv.append("--skip-if-exists")
        ec = _run_backend(argv)
        if ec:
            return ec
    return 0


def _start_adapter_for_pack(pack: IntegrationPack) -> int:
    if pack.adapter is None:
        return 0
    try:
        start_adapter(pack)
    except AdapterError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def _start_adapters_for_configs(configs: list[Path]) -> int:
    for path in configs:
        # Adapter-only path: parent ``start --agent-config <dir>`` already started backend.
        pack = load_integration_pack(path)
        if pack.adapter is None:
            continue
        ec = _start_adapter_for_pack(pack)
        if ec:
            return ec
    return 0


def _start_pack(
    pack: IntegrationPack,
    *,
    seed: bool,
    skip_if_exists: bool,
) -> int:
    """Start backend + adapter for one integration pack with rollback on adapter failure."""
    ok, err, started_backend = ensure_backend_for_pack(pack, run_backend_start=_run_backend)
    if not ok:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    started_adapter = False
    agent_id = pack.agent.agent_id
    if pack.adapter is not None and not is_adapter_running(agent_id):
        ec = _start_adapter_for_pack(pack)
        if ec:
            if started_backend:
                _run_backend(["stop"])
            return ec
        started_adapter = True

    if seed:
        ec = _seed_agent_config(pack.agent.source_path, skip_if_exists=skip_if_exists)
        if ec:
            if started_adapter:
                stop_adapter(agent_id, quiet=True)
            if started_backend:
                _run_backend(["stop"])
            return ec

    return 0


def _rollback_start(pack: IntegrationPack) -> None:
    """Stop adapter + backend after a failed ``up`` (gateway is stopped if it started)."""
    stop_hermes_gateway(quiet=True)
    if pack.adapter is not None:
        stop_adapter(pack.agent.agent_id, quiet=True)
    _run_backend(["stop"])


def _gateway_status_line() -> str:
    if is_gateway_running():
        return "gateway: running"
    return "gateway: not running"


def _cmd_up(agent: str, *, seed: bool, skip_if_exists: bool) -> int:
    """Start IntentFrame runtime + adapter + Hermes gateway (chat-ready stack)."""
    if agent != "hermes":
        print(f"ERROR: up is only implemented for hermes (got {agent!r})", file=sys.stderr)
        return 1

    if (ec := _require_openai_api_key()) is not None:
        return ec

    pack = load_and_activate_pack(agent)
    ec = _start_pack(pack, seed=seed, skip_if_exists=skip_if_exists)
    if ec:
        return ec

    if resolve_hermes_bin() is None:
        print(
            "ERROR: Hermes CLI not found — run: intentframe-integrations install hermes",
            file=sys.stderr,
        )
        _rollback_start(pack)
        return 1

    try:
        start_hermes_gateway(pack)
    except HermesGatewayError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        _rollback_start(pack)
        return 1

    print(
        f"\nHermes + IntentFrame stack is up for agent {agent!r}.\n"
        f"Backend bridge: ~/.intentframe/backend/bridge.sock\n"
        f"{adapter_status_line(pack)}\n"
        f"{_gateway_status_line()}\n"
        f"Gateway log: {gateway_log_file()}\n"
        "Next: hermes dashboard   # http://localhost:9119/chat"
    )
    return 0


def _cmd_start(agent: str, *, seed: bool, skip_if_exists: bool) -> int:
    if (ec := _require_openai_api_key()) is not None:
        return ec

    # Env + Hermes manifest seed before backend inherits os.environ.
    pack = load_and_activate_pack(agent)

    ec = _start_pack(pack, seed=seed, skip_if_exists=skip_if_exists)
    if ec:
        return ec

    print(
        f"\nIntentFrame Integrations runtime is up for agent {agent!r}.\n"
        f"Backend bridge: ~/.intentframe/backend/bridge.sock\n"
        f"{adapter_status_line(pack)}\n"
        f"Next: bin/intentframe-integrations integrate {agent}\n"
        "Export env for Hermes, then restart your gateway."
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
    configs = iter_agent_configs(cfg)
    if not configs:
        print(f"ERROR: agent config not found: {cfg}", file=sys.stderr)
        return 1

    if cfg.is_file():
        pack = load_and_activate_pack_from_path(cfg)
        ec = _start_pack(pack, seed=seed, skip_if_exists=skip_if_exists)
        if ec:
            return ec
        print(
            f"\nIntentFrame Integrations runtime is up ({cfg}).\n"
            f"Backend bridge: ~/.intentframe/backend/bridge.sock\n"
            f"{adapter_status_line(pack)}"
        )
        return 0

    ec = _run_backend(["start", "--agent-config", str(cfg)])
    if ec:
        return ec

    ec = _start_adapters_for_configs(configs)
    if ec:
        return ec

    if seed:
        ec = _seed_agent_config(cfg, skip_if_exists=skip_if_exists)
        if ec:
            return ec

    print(
        f"\nIntentFrame Integrations runtime is up ({cfg}).\n"
        "Backend bridge: ~/.intentframe/backend/bridge.sock"
    )
    return 0


def _cmd_stop() -> int:
    stop_hermes_gateway(quiet=True)
    for agent in list_agents():
        stop_adapter(agent, quiet=True)
    return _run_backend(["stop"])


def _cmd_status() -> int:
    ec = _run_backend(["status"])
    for agent in list_agents():
        try:
            pack = load_and_activate_pack(agent)
        except (FileNotFoundError, ValueError):
            continue
        if pack.adapter is not None:
            print(adapter_status_line(pack))
    return ec


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


def _cmd_doctor(
    agent: str,
    *,
    require_hermes: bool = True,
    require_integration: bool = True,
) -> int:
    if agent == "hermes":
        pack = load_and_activate_pack("hermes")
        report = doctor_hermes(
            pack,
            require_hermes=require_hermes,
            require_integration=require_integration,
        )
        for line in report.lines:
            print(line)
        if not report.ok:
            print("\nExport env for Hermes:", file=sys.stderr)
            print(format_env_exports(pack), file=sys.stderr)
        return 0 if report.ok else 1

    pack = load_and_activate_pack(agent)
    bridge_socket = Path(os.path.expanduser("~/.intentframe/backend/bridge.sock"))

    print(f"Repo agent config: {pack.agent.source_path}")
    print(f"  agent_id:  {pack.agent.agent_id}")
    print(f"  user_id:   {pack.agent.user_id}")

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


def _cmd_policy_show(agent: str) -> int:
    try:
        report = policy_show(agent)
    except (PolicyError, FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(format_policy_show(report))
    return 0


def _cmd_policy_reload(agent: str) -> int:
    try:
        path = policy_reload(agent)
    except (PolicyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Policy reloaded from {path}")
    print("Changes apply immediately (no gateway or adapter restart needed).")
    return 0


def _cmd_policy_set(agent: str, policy_path: Path) -> int:
    try:
        path = policy_set(agent, policy_path)
    except (PolicyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Policy installed to {path} and loaded into registry")
    print("Changes apply immediately (no gateway or adapter restart needed).")
    return 0


def _cmd_policy_reset(agent: str) -> int:
    try:
        path = policy_reset(agent)
    except (PolicyError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Policy reset to shipped default at {path} and loaded into registry")
    print("Changes apply immediately (no gateway or adapter restart needed).")
    return 0


def _cmd_integrate(
    agent: str,
    *,
    copy: bool,
    skip_config: bool,
    reset_governance: bool,
    reset_policy: bool,
) -> int:
    if agent != "hermes":
        print(f"ERROR: integrate is only implemented for hermes (got {agent!r})", file=sys.stderr)
        return 1

    pack = load_and_activate_pack("hermes")
    try:
        result = integrate_hermes(
            pack,
            copy=copy,
            skip_config=skip_config,
            reset_governance=reset_governance,
            reset_policy=reset_policy,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: integration command failed: {exc}", file=sys.stderr)
        return 1

    for msg in result.messages:
        print(msg)

    print("\nEnvironment applied for this process:")
    print(format_env_exports(pack))
    print("\nThen restart your Hermes gateway (e.g. intentframe-integrations gateway start hermes).")
    return 0


def _cmd_install_hermes(*, version: str | None, force: bool) -> int:
    try:
        result = install_hermes_agent(version=version, force=force)
    except HermesInstallError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as exc:
        print(f"ERROR: Hermes install command failed: {exc}", file=sys.stderr)
        return 1

    for msg in result.messages:
        print(msg)

    print("\nNext:")
    print("  bin/intentframe-integrations start hermes")
    print("  bin/intentframe-integrations integrate hermes")
    print("  bin/intentframe-integrations gateway start hermes --api-server")
    return 0


def _cmd_gateway_start(
    agent: str,
    *,
    api_server: bool,
    api_port: int | None,
    api_key: str | None,
    detach: bool,
    gateway_args: list[str],
) -> int:
    if agent != "hermes":
        print(f"ERROR: gateway start is only implemented for hermes (got {agent!r})", file=sys.stderr)
        return 1

    pack = load_and_activate_pack("hermes")

    if resolve_hermes_bin() is None:
        print(
            "ERROR: Hermes CLI not found — run: intentframe-integrations install hermes",
            file=sys.stderr,
        )
        return 1

    try:
        start_hermes_gateway(
            pack,
            detach=detach,
            api_server=api_server,
            api_key=api_key,
            api_port=api_port,
            gateway_args=gateway_args,
        )
    except HermesGatewayError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_gateway_stop(agent: str) -> int:
    if agent != "hermes":
        print(f"ERROR: gateway stop is only implemented for hermes (got {agent!r})", file=sys.stderr)
        return 1
    stop_hermes_gateway()
    return 0


def _cmd_governance_list(agent: str) -> int:
    if agent != "hermes":
        print(f"ERROR: governance is only implemented for hermes (got {agent!r})", file=sys.stderr)
        return 1
    try:
        entries = list_governed_tools(agent)
    except GovernanceEditError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Governed tool catalog ({agent}):")
    for name, enabled in entries:
        state = "enabled" if enabled else "disabled"
        print(f"  {name:15} {state}")

    governed = runtime_governed_tool_names(agent)
    print(f"\nGoverned at runtime: {', '.join(governed) if governed else '(none)'}")
    return 0


def _cmd_governance_set(agent: str, tool: str, *, enabled: bool) -> int:
    if agent != "hermes":
        print(f"ERROR: governance is only implemented for hermes (got {agent!r})", file=sys.stderr)
        return 1
    try:
        path = set_tool_enabled(tool, enabled, agent_id=agent)
    except GovernanceEditError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    state = "enabled" if enabled else "disabled"
    print(f"Set {tool!r} to {state} in {path}")
    print(
        "Restart Hermes gateway and adapter for changes to take effect "
        "(governance is loaded at process start)."
    )
    return 0


def _ensure_runtime(pack: IntegrationPack) -> int:
    if backend_ready_for_pack(pack) and (
        pack.adapter is None or is_adapter_running(pack.agent.agent_id)
    ):
        return 0

    ok, err, _started_backend = ensure_backend_for_pack(pack, run_backend_start=_run_backend)
    if not ok:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    if pack.adapter is not None and not is_adapter_running(pack.agent.agent_id):
        ec = _start_adapter_for_pack(pack)
        if ec:
            return ec

    if not backend_ready_for_pack(pack):
        print("ERROR: IntentFrame runtime is not ready for this agent.", file=sys.stderr)
        return 1
    return 0


def _cmd_run(agent: str, *, gateway_args: list[str]) -> int:
    if agent != "hermes":
        print(f"ERROR: run is only implemented for hermes (got {agent!r})", file=sys.stderr)
        return 1

    if (ec := _require_openai_api_key()) is not None:
        return ec

    pack = load_and_activate_pack("hermes")

    ec = _ensure_runtime(pack)
    if ec:
        return ec

    ec = _cmd_integrate(agent, copy=False, skip_config=False, reset_governance=False)
    if ec:
        return ec

    if resolve_hermes_bin() is None:
        ec = _cmd_install_hermes(version=None, force=False)
        if ec:
            return ec

    binary = resolve_hermes_bin()
    if binary is None:
        print(
            "ERROR: Hermes CLI not found after install — run: intentframe-integrations install hermes",
            file=sys.stderr,
        )
        return 1

    cmd = [str(binary), "gateway", *normalize_hermes_gateway_argv(gateway_args)]
    env = os.environ.copy()
    from intentframe_integrations.hermes_paths import hermes_home

    env["HERMES_HOME"] = str(hermes_home())
    print(f"\nLaunching: {' '.join(cmd)}", file=sys.stderr)
    print("Hermes plugin env is applied to this process.", file=sys.stderr)
    try:
        return subprocess.call(cmd, env=env)
    except KeyboardInterrupt:
        return 130


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
        help="Start validate runtime + bridge + agent adapter",
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

    p_up = sub.add_parser(
        "up",
        help="Start IntentFrame runtime + adapter + Hermes gateway (ready for hermes dashboard)",
    )
    p_up.add_argument("agent", choices=agents, help="Integration profile (hermes)")
    p_up.add_argument(
        "--no-seed",
        action="store_true",
        help="Skip seed-policy after start",
    )
    p_up.add_argument(
        "--skip-if-exists",
        action="store_true",
        help="Pass --skip-if-exists to seed-policy",
    )

    sub.add_parser("stop", help="Stop agent adapters, IntentFrame runtime, and bridge")
    sub.add_parser("status", help="Runtime, bridge, and adapter status")

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
    p_doctor.add_argument(
        "--install-only",
        action="store_true",
        help="Check Hermes install only (skip IntentFrame integration requirements)",
    )

    p_install = sub.add_parser(
        "install",
        help="Install Hermes Agent into the orchestrator-managed environment",
    )
    p_install.add_argument("agent", choices=agents)
    p_install.add_argument(
        "--version",
        default=None,
        help="Hermes Agent version to install (default: pinned release)",
    )
    p_install.add_argument(
        "--force",
        action="store_true",
        help="Reinstall Hermes Agent even if already present",
    )

    p_integrate = sub.add_parser(
        "integrate",
        help="Install Hermes plugin, sync adapter venv, merge ~/.hermes/config.yaml",
    )
    p_integrate.add_argument("agent", choices=agents)
    p_integrate.add_argument(
        "--copy",
        action="store_true",
        help="Copy plugin instead of symlinking",
    )
    p_integrate.add_argument(
        "--skip-config",
        action="store_true",
        help="Do not merge ~/.hermes/config.yaml",
    )
    p_integrate.add_argument(
        "--reset-governance",
        action="store_true",
        help="Overwrite runtime governance/tools.yaml from the default template (default: keep user config)",
    )
    p_integrate.add_argument(
        "--reset-policy",
        action="store_true",
        help="Overwrite runtime policy.yaml from the shipped default (default: keep user config)",
    )

    p_policy = sub.add_parser(
        "policy",
        help="Show, set, reload, or reset runtime agent policy.yaml",
    )
    policy_sub = p_policy.add_subparsers(dest="policy_command", required=True)

    p_policy_show = policy_sub.add_parser("show", help="Show runtime policy path and registry status")
    p_policy_show.add_argument("agent", choices=agents)

    p_policy_reload = policy_sub.add_parser(
        "reload",
        help="Load runtime policy.yaml into policy-registry (after hand-editing)",
    )
    p_policy_reload.add_argument("agent", choices=agents)

    p_policy_set = policy_sub.add_parser(
        "set",
        help="Copy a policy file to runtime and load into policy-registry",
    )
    p_policy_set.add_argument("agent", choices=agents)
    p_policy_set.add_argument("path", type=Path, help="Path to policy YAML")

    p_policy_reset = policy_sub.add_parser(
        "reset",
        help="Restore shipped default policy to runtime and load into registry",
    )
    p_policy_reset.add_argument("agent", choices=agents)

    p_run = sub.add_parser(
        "run",
        help="Start IF runtime, integrate plugin, and launch agent (Hermes: hermes gateway)",
    )
    p_run.add_argument("agent", choices=agents)
    p_run.add_argument(
        "gateway_args",
        nargs=argparse.REMAINDER,
        help="Extra args passed to hermes gateway (after --)",
    )

    p_gateway = sub.add_parser("gateway", help="Manage Hermes gateway lifecycle")
    gateway_sub = p_gateway.add_subparsers(dest="gateway_command", required=True)

    p_gateway_start = gateway_sub.add_parser(
        "start",
        help="Start Hermes gateway in the background",
    )
    p_gateway_start.add_argument("agent", choices=agents)
    p_gateway_start.add_argument(
        "--api-server",
        action="store_true",
        help="Enable Hermes API server and wait for /health",
    )
    p_gateway_start.add_argument(
        "--api-port",
        type=int,
        default=None,
        help="API server port (default: 8642)",
    )
    p_gateway_start.add_argument(
        "--api-key",
        default=None,
        help="API server key (default: INTENTFRAME_HERMES_API_KEY or generated local key)",
    )
    p_gateway_start.add_argument(
        "--no-detach",
        action="store_true",
        help="Run gateway in foreground (blocks until gateway exits)",
    )
    p_gateway_start.add_argument(
        "gateway_args",
        nargs=argparse.REMAINDER,
        help="Extra args passed to hermes gateway (after --)",
    )

    p_gateway_stop = gateway_sub.add_parser("stop", help="Stop orchestrator-managed Hermes gateway")
    p_gateway_stop.add_argument("agent", choices=agents)

    p_governance = sub.add_parser(
        "governance",
        help="List or enable/disable governed Hermes tools in governance/tools.yaml",
    )
    governance_sub = p_governance.add_subparsers(dest="governance_command", required=True)

    p_governance_list = governance_sub.add_parser("list", help="Show catalog and runtime governed tools")
    p_governance_list.add_argument("agent", choices=agents)

    p_governance_enable = governance_sub.add_parser("enable", help="Enable a governed tool")
    p_governance_enable.add_argument("agent", choices=agents)
    p_governance_enable.add_argument("tool", help="Hermes tool name from governance/tools.yaml")

    p_governance_disable = governance_sub.add_parser("disable", help="Disable a governed tool")
    p_governance_disable.add_argument("agent", choices=agents)
    p_governance_disable.add_argument("tool", help="Hermes tool name from governance/tools.yaml")

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
        case "up":
            return _cmd_up(
                args.agent,
                seed=not args.no_seed,
                skip_if_exists=args.skip_if_exists,
            )
        case "stop":
            return _cmd_stop()
        case "status":
            return _cmd_status()
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
            if args.agent != "hermes":
                return _cmd_doctor(args.agent)
            return _cmd_doctor(
                args.agent,
                require_hermes=True,
                require_integration=not args.install_only,
            )
        case "install":
            if args.agent != "hermes":
                print(f"ERROR: install is only implemented for hermes (got {args.agent!r})", file=sys.stderr)
                return 1
            return _cmd_install_hermes(version=args.version, force=args.force)
        case "integrate":
            return _cmd_integrate(
                args.agent,
                copy=args.copy,
                skip_config=args.skip_config,
                reset_governance=args.reset_governance,
                reset_policy=args.reset_policy,
            )
        case "policy":
            match args.policy_command:
                case "show":
                    return _cmd_policy_show(args.agent)
                case "reload":
                    return _cmd_policy_reload(args.agent)
                case "set":
                    return _cmd_policy_set(args.agent, args.path)
                case "reset":
                    return _cmd_policy_reset(args.agent)
                case _:
                    parser.error(f"Unknown policy command: {args.policy_command}")
                    return 2
        case "run":
            gateway_args = args.gateway_args
            if gateway_args and gateway_args[0] == "--":
                gateway_args = gateway_args[1:]
            return _cmd_run(args.agent, gateway_args=gateway_args)
        case "gateway":
            match args.gateway_command:
                case "start":
                    gateway_args = args.gateway_args
                    if gateway_args and gateway_args[0] == "--":
                        gateway_args = gateway_args[1:]
                    return _cmd_gateway_start(
                        args.agent,
                        api_server=args.api_server,
                        api_port=args.api_port,
                        api_key=args.api_key,
                        detach=not args.no_detach,
                        gateway_args=gateway_args,
                    )
                case "stop":
                    return _cmd_gateway_stop(args.agent)
                case _:
                    parser.error(f"Unknown gateway command: {args.gateway_command}")
                    return 2
        case "governance":
            match args.governance_command:
                case "list":
                    return _cmd_governance_list(args.agent)
                case "enable":
                    return _cmd_governance_set(args.agent, args.tool, enabled=True)
                case "disable":
                    return _cmd_governance_set(args.agent, args.tool, enabled=False)
                case _:
                    parser.error(f"Unknown governance command: {args.governance_command}")
                    return 2
        case _:
            parser.error(f"Unknown command: {args.command}")
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
