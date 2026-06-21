#!/usr/bin/env python3
"""Hermes gateway E2E: production CLI journey + /v1/responses ALLOW/BLOCK."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from api_client import (  # noqa: E402
    get_capabilities,
    run_allow_with_retries,
    run_block_once,
    wait_health,
)
from cli_runner import CliError, format_diagnostics, log_sandbox_paths, run_cli, step, stop_everything  # noqa: E402
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
    expose_external_hermes_bin,
    record_runtime_pids,
    seed_hermes_openai_for_e2e,
)
from isolation import _e2e_openai_model  # noqa: E402

PLUGIN_KEY = "intentframe-terminal"
API_HOST = "127.0.0.1"
INSTALL_TIMEOUT = 600.0
GATEWAY_START_TIMEOUT = 300.0


def _require_openai_api_key() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("ERROR: OPENAI_API_KEY is required for Hermes gateway E2E")


def _activate_sandbox(env: IsolatedEnv) -> None:
    step(f"Activating sandbox HOME={env.home} HERMES_HOME={env.hermes_home}")
    activate(env)
    step(f"Seeding Hermes OpenAI provider (model={_e2e_openai_model()})")
    seed_hermes_openai_for_e2e(env)
    assert_hermes_openai_seeded(env)
    step(f"Sandbox ready (API port={env.api_port})")
    log_sandbox_paths(env, when="activate — paths appear as services start")


def _plugin_enabled(config_path: Path) -> bool:
    if not config_path.is_file():
        return False
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return False
    plugins = raw.get("plugins")
    if not isinstance(plugins, dict):
        return False
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        return False
    return enabled.count(PLUGIN_KEY) == 1


def _assert_plugin_state(env: IsolatedEnv) -> None:
    if not env.plugin_install_path.exists():
        raise AssertionError(f"Plugin not installed at {env.plugin_install_path}")
    if not _plugin_enabled(env.hermes_config_path):
        raise AssertionError(f"Plugin {PLUGIN_KEY!r} not enabled in {env.hermes_config_path}")
    if not env.managed_hermes_bin.is_file():
        raise AssertionError(f"Managed Hermes binary missing: {env.managed_hermes_bin}")


def _assert_managed_hermes_selected(env: IsolatedEnv) -> None:
    doctor = run_cli(["doctor", "hermes", "--install-only"], env=env, stream=False)
    if str(env.managed_hermes_bin) not in doctor.stdout:
        raise AssertionError(
            "Doctor did not resolve the sandbox managed Hermes binary.\n"
            f"Expected: {env.managed_hermes_bin}\n"
            f"Output:\n{doctor.stdout}"
        )


def _assert_external_hermes_selected(env: IsolatedEnv, external_bin: Path) -> None:
    doctor = run_cli(["doctor", "hermes", "--install-only"], env=env, stream=False)
    if str(external_bin) not in doctor.stdout:
        raise AssertionError(
            "Doctor did not resolve the external HERMES_BIN binary.\n"
            f"Expected: {external_bin}\n"
            f"Output:\n{doctor.stdout}"
        )


def _assert_doctor_fails_plugin_missing(env: IsolatedEnv) -> None:
    result = run_cli(["doctor", "hermes"], env=env, expect_code=1, stream=False)
    combined = f"{result.stdout}\n{result.stderr}"
    if "plugin install: missing" not in combined.lower():
        raise AssertionError(
            "Expected doctor to fail with plugin install missing before integrate.\n"
            f"Output:\n{combined}"
        )


def _gateway_start(env: IsolatedEnv, *, label: str) -> None:
    step(f"{label}: gateway start hermes --api-server (port {env.api_port})")
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


def _gateway_stop(env: IsolatedEnv, *, label: str) -> None:
    step(f"{label}: gateway stop hermes")
    run_cli(["gateway", "stop", "hermes"], env=env, stream=False)


def _run_api_allow_block(env: IsolatedEnv, *, label: str) -> None:
    log_sandbox_paths(
        env,
        when=f"{label} before /v1/responses — tail intentframe-server + gateway for tool calls",
    )
    step(f"{label}: GET /v1/capabilities")
    caps = get_capabilities(host=API_HOST, port=env.api_port, api_key=env.api_key)
    if not caps:
        raise AssertionError("Empty /v1/capabilities response")

    marker = f"intentframe-hermes-e2e-ok-{env.run_id}"
    step(f"{label}: POST /v1/responses ALLOW (LLM → terminal → adapter → bridge)")
    run_allow_with_retries(host=API_HOST, port=env.api_port, api_key=env.api_key, marker=marker)

    step(f"{label}: POST /v1/responses BLOCK (policy should deny sudo)")
    run_block_once(host=API_HOST, port=env.api_port, api_key=env.api_key)


def _install_hermes(env: IsolatedEnv, *, label: str) -> None:
    step(f"{label}: install hermes")
    run_cli(["install", "hermes"], env=env, timeout=INSTALL_TIMEOUT)


def _integrate_hermes(env: IsolatedEnv, *, label: str) -> None:
    step(f"{label}: integrate hermes")
    run_cli(["integrate", "hermes"], env=env, timeout=INSTALL_TIMEOUT)


def _start_runtime(env: IsolatedEnv, *, label: str) -> None:
    step(f"{label}: start hermes (IntentFrame backend + adapter)")
    run_cli(["start", "hermes", "--skip-if-exists"], env=env, timeout=GATEWAY_START_TIMEOUT)
    record_runtime_pids(env)


def _doctor_full(env: IsolatedEnv, *, label: str) -> None:
    step(f"{label}: doctor hermes")
    run_cli(["doctor", "hermes"], env=env, stream=False)


def pass1_greenfield(env: IsolatedEnv) -> None:
    step("Pass 1 — greenfield: no Hermes on PATH, full install journey")

    step("Pass 1: assert no system Hermes on isolated PATH")
    assert_no_system_hermes_on_path()

    step("Pass 1: doctor --install-only before install (expect fail)")
    run_cli(["doctor", "hermes", "--install-only"], env=env, expect_code=1, stream=False)

    _install_hermes(env, label="Pass 1")

    step("Pass 1: doctor --install-only after install (expect pass)")
    _assert_managed_hermes_selected(env)

    _start_runtime(env, label="Pass 1")
    _integrate_hermes(env, label="Pass 1")
    _doctor_full(env, label="Pass 1")
    step("Pass 1: verify plugin installed and enabled")
    _assert_plugin_state(env)

    _gateway_start(env, label="Pass 1")
    _run_api_allow_block(env, label="Pass 1")
    _gateway_stop(env, label="Pass 1")


def pass2a_reuse_install(env: IsolatedEnv) -> None:
    step("Pass 2a — idempotent install/integrate on same sandbox")

    step("Pass 2a: install hermes (expect already installed)")
    install = run_cli(["install", "hermes"], env=env, timeout=INSTALL_TIMEOUT, stream=False)
    if "already installed" not in install.stdout.lower():
        raise AssertionError(f"Expected idempotent install message, got:\n{install.stdout}")

    _integrate_hermes(env, label="Pass 2a")
    _doctor_full(env, label="Pass 2a")
    step("Pass 2a: verify plugin state")
    _assert_plugin_state(env)

    _gateway_start(env, label="Pass 2a")
    _run_api_allow_block(env, label="Pass 2a")
    _gateway_stop(env, label="Pass 2a")


def pass2b_external_hermes(env: IsolatedEnv) -> None:
    step("Pass 2b — external HERMES_BIN simulation (symlinked managed binary), first-time integrate")

    _install_hermes(env, label="Pass 2b")

    step("Pass 2b: expose external HERMES_BIN simulation (symlink to managed install)")
    external_bin = expose_external_hermes_bin(env)
    _assert_external_hermes_selected(env, external_bin)

    step("Pass 2b: doctor before integrate (expect fail — plugin missing)")
    _assert_doctor_fails_plugin_missing(env)

    _start_runtime(env, label="Pass 2b")
    _integrate_hermes(env, label="Pass 2b")
    _doctor_full(env, label="Pass 2b")
    step("Pass 2b: verify plugin state")
    _assert_plugin_state(env)

    _gateway_start(env, label="Pass 2b")
    _run_api_allow_block(env, label="Pass 2b")
    _gateway_stop(env, label="Pass 2b")


def main() -> int:
    _require_openai_api_key()

    env1: IsolatedEnv | None = None
    env2: IsolatedEnv | None = None
    exit_code = 1

    try:
        env1 = create_isolated_env()
        _activate_sandbox(env1)
        pass1_greenfield(env1)

        pass2a_reuse_install(env1)

        step("Pass 1/2a cleanup: stop runtime and verify sandbox artifacts removed")
        stop_everything(env=env1)
        assert_runtime_stopped(env1)
        deactivate(env1)

        env2 = create_isolated_env()
        _activate_sandbox(env2)
        pass2b_external_hermes(env2)

        step("Pass 2b cleanup: stop runtime and verify sandbox artifacts removed")
        stop_everything(env=env2)
        assert_runtime_stopped(env2)
        deactivate(env2)

        assert_real_state_untouched(env1)
        assert_real_state_untouched(env2)
        exit_code = 0
        print("\n==> Hermes gateway E2E passed (pass 1, 2a, 2b)", file=sys.stderr)
    except (CliError, AssertionError, TimeoutError, RuntimeError) as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        for env in (env1, env2):
            if env is None:
                continue
            diagnostics = format_diagnostics(env)
            if diagnostics:
                print("\n==> Diagnostics", file=sys.stderr)
                print(diagnostics, file=sys.stderr)
        exit_code = 1
    finally:
        for env in (env1, env2):
            if env is None:
                continue
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
        if env1 is not None:
            try:
                assert_real_state_untouched(env1)
            except AssertionError as exc:
                print(f"\nERROR: {exc}", file=sys.stderr)
                exit_code = 1
        if env2 is not None:
            try:
                assert_real_state_untouched(env2)
            except AssertionError as exc:
                print(f"\nERROR: {exc}", file=sys.stderr)
                exit_code = 1

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
