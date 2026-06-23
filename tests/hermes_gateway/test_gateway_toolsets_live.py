#!/usr/bin/env python3
"""Live gateway test: toolsets, schema probe, and provider tools= payload."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from api_client import (  # noqa: E402
    assert_intentframe_gate_toolsets,
    get_toolsets,
    post_responses,
    wait_health,
)
from provider_request_contract import (  # noqa: E402
    assert_gateway_openai_roundtrip,
    assert_provider_tools_surface,
    format_gateway_roundtrip_snapshot,
    format_provider_tools_snapshot,
    load_newest_request_dump,
    load_request_dump,
    request_dump_paths,
)
from cli_runner import CliError, format_diagnostics, run_cli, step, stop_everything  # noqa: E402
from isolation import (  # noqa: E402
    IsolatedEnv,
    activate,
    assert_hermes_openai_seeded,
    assert_no_system_hermes_on_path,
    assert_real_state_untouched,
    assert_runtime_stopped,
    cleanup_tree,
    create_isolated_env,
    deactivate,
    record_runtime_pids,
    seed_hermes_openai_for_e2e,
)
from isolation import _e2e_openai_model  # noqa: E402
from toolsets_contract import format_toolsets_snapshot, parse_toolsets_response  # noqa: E402

_TESTS_DIR = HERE.parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))
from hermes_governance_fixtures import gateway_e2e_probe_tool_names  # noqa: E402

API_HOST = "127.0.0.1"
INSTALL_TIMEOUT = 600.0
GATEWAY_START_TIMEOUT = 300.0
PROBE_SCRIPT = HERE / "probe_hermes_tool_schemas.py"


def _require_openai_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("ERROR: OPENAI_API_KEY is required for Hermes gateway toolsets live test")


def _hermes_python(env: IsolatedEnv) -> Path:
    scripts = "Scripts" if os.name == "nt" else "bin"
    return env.integration_state / "hermes-agent-venv" / scripts / "python"


def _run_schema_probe(env: IsolatedEnv) -> None:
    python = _hermes_python(env)
    if not python.is_file():
        raise AssertionError(f"Hermes venv python missing: {python}")
    if not PROBE_SCRIPT.is_file():
        raise AssertionError(f"Probe script missing: {PROBE_SCRIPT}")

    step("Probe Hermes registry schemas (reason injection + gate markers)")
    result = subprocess.run(
        [str(python), str(PROBE_SCRIPT)],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=120.0,
        check=False,
    )
    if result.stdout.strip():
        print(result.stdout.strip(), file=sys.stderr)
    if result.returncode != 0:
        raise AssertionError(
            f"Schema probe failed (exit {result.returncode}).\n"
            f"stderr:\n{result.stderr[-4000:]}"
        )


def main() -> int:
    _require_openai_api_key()

    env: IsolatedEnv | None = None
    exit_code = 1

    try:
        env = create_isolated_env()
        step(f"Activating sandbox HOME={env.home} HERMES_HOME={env.hermes_home}")
        activate(env)
        step(f"Seeding Hermes OpenAI provider (model={_e2e_openai_model()})")
        seed_hermes_openai_for_e2e(env)
        assert_hermes_openai_seeded(env)

        step("Assert no system Hermes on isolated PATH")
        assert_no_system_hermes_on_path()

        step("install hermes")
        run_cli(["install", "hermes"], env=env, timeout=INSTALL_TIMEOUT)

        step("start hermes (IntentFrame backend + adapter)")
        run_cli(["start", "hermes", "--skip-if-exists"], env=env, timeout=GATEWAY_START_TIMEOUT)
        record_runtime_pids(env)

        step("integrate hermes (intentframe-gate)")
        run_cli(["integrate", "hermes"], env=env, timeout=INSTALL_TIMEOUT)

        os.environ["HERMES_DUMP_REQUESTS"] = "1"

        step(f"gateway start hermes --api-server (port {env.api_port})")
        run_cli(
            [
                "gateway",
                "start",
                "hermes",
                "--api-server",
                "--api-port",
                str(env.api_port),
                "--api-key",
                env.api_key,
            ],
            env=env,
            timeout=GATEWAY_START_TIMEOUT,
        )
        record_runtime_pids(env)
        wait_health(host=API_HOST, port=env.api_port, api_key=env.api_key)

        step("GET /v1/toolsets")
        body = get_toolsets(host=API_HOST, port=env.api_port, api_key=env.api_key)
        assert_intentframe_gate_toolsets(body)
        snapshot = parse_toolsets_response(body)
        print("\n==> Toolsets snapshot (enabled toolsets)", file=sys.stderr)
        print(format_toolsets_snapshot(snapshot), file=sys.stderr)

        _run_schema_probe(env)

        existing_dumps = frozenset(request_dump_paths(env.hermes_home))
        step("POST /v1/responses (capture provider tools= for OpenAI)")
        responses_body = post_responses(
            host=API_HOST,
            port=env.api_port,
            api_key=env.api_key,
            prompt="Reply with the single word OK. Do not call any tools.",
            instructions="Automated integration test. Do not use tools.",
        )
        assert_gateway_openai_roundtrip(responses_body)
        governed = gateway_e2e_probe_tool_names()
        dump_path, provider_body = load_newest_request_dump(
            env.hermes_home,
            existing=existing_dumps,
        )
        dump_raw = load_request_dump(dump_path)
        request_meta = dump_raw.get("request")
        request_meta_dict = request_meta if isinstance(request_meta, dict) else {}
        assert_provider_tools_surface(
            provider_body,
            governed,
            expected_model=_e2e_openai_model(),
        )
        provider_url = request_meta_dict.get("url")
        if not isinstance(provider_url, str):
            provider_url = None
        print(
            "\n==> OpenAI round-trip proof\n"
            + format_gateway_roundtrip_snapshot(
                responses_body,
                provider_url=provider_url,
                expected_model=_e2e_openai_model(),
            ),
            file=sys.stderr,
        )
        print(
            "\n==> Provider tools= snapshot (OpenAI upstream payload)\n"
            + format_provider_tools_snapshot(
                provider_body,
                governed,
                dump_path=dump_path,
            ),
            file=sys.stderr,
        )

        assert_real_state_untouched(env)
        exit_code = 0
        print("\n==> Hermes gateway toolsets live test passed", file=sys.stderr)
    except (CliError, AssertionError, TimeoutError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        if env is not None:
            diagnostics = format_diagnostics(env)
            if diagnostics:
                print("\n==> Diagnostics", file=sys.stderr)
                print(diagnostics, file=sys.stderr)
        exit_code = 1
    finally:
        if env is not None:
            activate(env)
            try:
                stop_everything(env=env)
                assert_runtime_stopped(env)
            except AssertionError as exc:
                print(f"\nERROR: {exc}", file=sys.stderr)
                exit_code = 1
            finally:
                deactivate(env)
                cleanup_tree(env)
                try:
                    assert_real_state_untouched(env)
                except AssertionError as exc:
                    print(f"\nERROR: {exc}", file=sys.stderr)
                    exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
