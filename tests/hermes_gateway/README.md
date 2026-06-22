# Hermes gateway E2E

Opt-in end-to-end test for the **production CLI journey** plus real `/v1/responses`
ALLOW/BLOCK through Hermes gateway, the IntentFrame plugin, adapter, and backend.

Primary entrypoint: `test_gateway_e2e.py`. Shell wrapper: `tests/scripts/test-hermes-gateway-e2e.sh`.

## Run

From repo root (requires `OPENAI_API_KEY`):

```bash
RUN_HERMES_GATEWAY_E2E=1 \
  uv run --with httpx --package intentframe-integrations-cli \
  python tests/hermes_gateway/test_gateway_e2e.py
```

Or via the shell wrapper:

```bash
RUN_HERMES_GATEWAY_E2E=1 ./tests/scripts/test-hermes-gateway-e2e.sh
```

### Governance / scoped LLM probes

**Governed tools** = IntentFrame plugin gate active (see
[`docs/agent-tool-gating.md`](../../docs/agent-tool-gating.md#terminology-what-governed-means)).
This E2E harness does **not** toggle Hermes `/v1/toolsets`.

By default the test writes a **throwaway all-governed** governance yaml and sets
`HERMES_GOVERNANCE_YAML` in the test runner environment before `integrate` /
`gateway start` (same idea as catalog live tests). Real `~/.intentframe` runtime
config is not used.

Before starting the adapter or gateway, the harness calls
`assert_governance_env_contract()` (`governance_e2e_setup.py`): the path in
`os.environ["HERMES_GOVERNANCE_YAML"]` must match the governance snapshot and must
be the same value that `build_gateway_env()` and `_adapter_env()` would pass to
child processes. This catches wiring drift between the E2E runner, CLI, adapter,
and gateway.

This controls **IntentFrame plugin governance** (which Hermes tools pass through
the validate-only gate). It does **not** enable/disable Hermes native tools on
`/v1/toolsets` — ungoverned tools may still appear there and run without the gate.

| Variable | Effect |
|----------|--------|
| *(unset)* | Temp yaml with **all** catalog tools IntentFrame-governed |
| `HERMES_E2E_GOVERNED_TOOLS=terminal,process` | Temp yaml with only those tools governed; LLM probes run for that subset |
| `HERMES_GOVERNANCE_YAML=/path/to/tools.yaml` | Use your yaml as-is; skip auto-generation |

Examples:

```bash
# All governed tools (default)
RUN_HERMES_GATEWAY_E2E=1 ./tests/scripts/test-hermes-gateway-e2e.sh

# Only terminal + process LLM probes (IntentFrame-governed subset)
HERMES_E2E_GOVERNED_TOOLS=terminal,process \
  RUN_HERMES_GATEWAY_E2E=1 ./tests/scripts/test-hermes-gateway-e2e.sh
```

Included in the main pipeline when opted in:

```bash
RUN_HERMES_GATEWAY_E2E=1 ./scripts/e2e.sh
```

## What it covers

| Pass | Scenario |
|------|----------|
| **1** | Greenfield: `install` → `start` → `integrate` → `doctor` → `gateway start --api-server` → `/v1/responses` |
| **2a** | Reuse managed install from pass 1 (idempotent `integrate`, gateway restart) |
| **2b** | External Hermes via `HERMES_BIN`, then `integrate` and gateway E2E |

Each pass runs HTTP assertions against the gateway API for **IntentFrame-governed**
tools only (see `runtime_governed_tool_names()` in `_run_api_allow_block`). With
the default temp yaml that is all catalog tools; use `HERMES_E2E_GOVERNED_TOOLS`
to scope LLM probes.

| Tool | Deterministic ALLOW probe | Deterministic BLOCK probe | Semantic (ALLOW or BLOCK) |
|------|---------------------------|---------------------------|---------------------------|
| `terminal` | `printf '<marker>'` | `sudo echo …` | — |
| `process` | `action: list` | `action: run`, `data` contains `sudo` | — |
| `write_file` | path under `~/…` | path under `/etc/…` | — |
| `delete_file` | — | path under `/etc/…` | path under `~/…` |
| `patch` (replace) | replace under `~/…` | replace under `/etc/…` | — |
| `patch` (V4A mixed) | — | Update `~/…` + Delete `/etc/…` (fail-closed batch) | Update `~/…` + Delete `~/…` (per-intent AE/Guardian; batch fails if any op BLOCKs) |

Multi-intent `patch` calls map to multiple IntentFrame `/validate` requests inside the adapter;
the plugin still sees one allow/block for the single Hermes tool call.

## Sandbox isolation

Each run creates a disposable tree under `/tmp/hg{8-char-id}/` (short path for macOS UDS limits):

- `HOME` → `$test_root/home`
- `HERMES_HOME` → `$test_root/home/.hermes`

Real `~/.hermes` and `~/.intentframe/integrations/hermes` are snapshotted before the run and
asserted unchanged after cleanup. System `hermes` on `PATH` is hidden during greenfield install.

Cleanup removes **only that run's** `test_root`, not other `/tmp/hg*` sandboxes.

## Log paths (important)

E2E uses sandbox paths, **not** your real `~/.intentframe`. The test prints a catalog at
sandbox activation and again before `/v1/responses`:

| Label | Path (under sandbox) |
|-------|----------------------|
| Hermes gateway | `$HOME/.intentframe/integrations/hermes/gateway.log` |
| Hermes adapter | `$HOME/.intentframe/integrations/hermes/adapter.log` |
| IntentFrame bridge | `$HOME/.intentframe/backend/bridge.log` |
| IntentFrame supervisor | `$HOME/.intentframe/backend/supervisor.log` |
| IntentFrame executor | `$HOME/.intentframe/logs/executor.log` |
| IntentFrame core (policy/AE) | `$HOME/.intentframe/logs/intentframe-server.log` |
| Hermes config | `$HERMES_HOME/config.yaml` |
| Hermes `.env` | `$HERMES_HOME/.env` |

Example (paths vary per run):

```bash
tail -f /tmp/hg62012319/home/.intentframe/logs/intentframe-server.log
tail -f /tmp/hg62012319/home/.intentframe/integrations/hermes/gateway.log
```

On failure, `format_diagnostics()` in `cli_runner.py` also lists these paths (with secrets redacted from Hermes `.env`).

### Expected trace in `intentframe-server.log`

When `/v1/responses` reaches the plugin and adapter:

1. Adapter handshake on first validate
2. Four intent evaluations for the two ALLOW/BLOCK probes (two tool calls each in a typical run)

If the LLM fails before emitting a `terminal` function call, **IntentFrame logs may be empty**
for that request — tail `gateway.log` and OpenAI error text in test output instead.

## Hermes LLM config (test-only seed)

Production `integrate hermes` does **not** set Hermes model or provider. E2E seeds isolated
`$HERMES_HOME/config.yaml` before gateway start:

- `model.provider: openai-api`
- `model.api_mode: chat_completions`
- `model.name: gpt-4o-mini` (override with `INTENTFRAME_HERMES_E2E_MODEL`)

Hermes 0.17+ auto-selects OpenAI **Responses API** (`codex_responses`) for `api.openai.com`
unless `api_mode` is set. `gpt-4o-mini` does not support that mode (OpenAI 400:
"Encrypted content is not supported with this model"). The E2E seed avoids that mismatch.

IntentFrame backend uses its own `OPENAI_API_KEY` from the environment (Agents SDK / Responses API
for policy evaluation). That is separate from Hermes gateway LLM calls.

## Gateway lifecycle notes

`gateway start hermes` resolves to `hermes gateway run` (foreground runner). Service-style
subcommands passed through the orchestrator are stripped — see
`normalize_hermes_gateway_argv()` in `hermes_gateway.py`.

Startup waits on HTTP `/health` and process liveness; early exit dumps a tail of `gateway.log`.
Stop uses process-group termination (`start_new_session=True`) and verifies PID is still a
Hermes gateway before trusting stale PID files.

## Troubleshooting

| Symptom | Likely cause | Where to look |
|---------|--------------|---------------|
| Gateway health timeout | Wrong argv, crash on boot, port conflict | Sandbox `gateway.log`, test diagnostics |
| `/v1/responses` 400 from OpenAI | Responses API + unsupported model | `$HERMES_HOME/config.yaml` `api_mode` |
| ALLOW test: no `function_call` | LLM did not call `terminal` | `gateway.log`, retry logs in test output |
| BLOCK test passes but no IF log lines | Same — request never reached plugin | `gateway.log` first |
| Pass 2a idempotency failure | CLI stdout not captured | Fixed in `cli_runner.run_cli()` |
| Stale gateway after stop | PID reuse / wrong process | `_pid_is_hermes_gateway()` in `hermes_gateway.py` |
| Wrong governed set at runtime | Parent env not propagated to adapter/gateway | E2E `assert_governance_env_contract` failure; check `gateway start` stderr for `Hermes governance config:` line |

## Related docs

- `integrations/hermes/README.md` — integration architecture and manual checklist
- `intentframe-integrations-cli/README.md` — CLI command reference

## Unit tests (no network)

```bash
uv run --package intentframe-integrations-cli python tests/hermes_gateway/test_isolation.py
uv run --package intentframe-integrations-cli python tests/hermes_gateway/test_cli_runner.py
uv run --package intentframe-integrations-cli python tests/hermes_gateway/test_hermes_reference_contract.py
uv run --package intentframe-integrations-cli python tests/hermes_gateway/test_api_client.py
uv run --package intentframe-integrations-cli python tests/hermes_gateway/test_governed_tool_coverage.py
uv run --package intentframe-integrations-cli python tests/hermes_gateway/test_toolsets_contract.py
uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_scoped_governance_yaml.py
```

`test_scoped_governance_yaml.py` includes `assert_governance_env_contract` (env
parity with CLI child env builders). `test_hermes_install.py` covers
`build_gateway_env`, `_adapter_env`, and `format_env_exports` override behavior.

## Toolsets surface test (opt-in, no LLM)

Deterministic check of `GET /v1/toolsets` after `integrate hermes`, plus a Hermes-venv
schema probe that governed tools still use Hermes names with required `reason` and gate
markers. Does **not** call `/v1/responses`.

```bash
RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh
```

The full gateway E2E also asserts `/v1/toolsets` before the LLM probes.
