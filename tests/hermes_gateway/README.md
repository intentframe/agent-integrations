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
Integration guide: [`docs/hermes-intentframe-integration-guide.md`](../../docs/hermes-intentframe-integration-guide.md).
Plugin registration / preload: [`docs/hermes-plugin-registration-order.md`](../../docs/hermes-plugin-registration-order.md).
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
| `HERMES_E2E_GOVERNED_TOOLS=terminal,write_file` | Temp yaml with only those tools governed; LLM probes run for that subset |
| `HERMES_GOVERNANCE_YAML=/path/to/tools.yaml` | Use your yaml as-is; skip auto-generation |

Examples:

```bash
# All governed tools (default)
RUN_HERMES_GATEWAY_E2E=1 ./tests/scripts/test-hermes-gateway-e2e.sh

# Only terminal + write_file LLM probes (IntentFrame-governed subset)
HERMES_E2E_GOVERNED_TOOLS=terminal,write_file \
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
native-mapper tools only. Generic-mapper catalog tools (e.g. `cronjob`) are covered
by live adapter/plugin semantic smoke — no gateway LLM probe. With the default temp
yaml all catalog tools are governed; use `HERMES_E2E_GOVERNED_TOOLS` to scope LLM probes.

| Tool | Deterministic ALLOW probe | Deterministic BLOCK probe | Semantic (ALLOW or BLOCK) |
|------|---------------------------|---------------------------|---------------------------|
| `terminal` | `printf '<marker>'` | `sudo echo …` | — |
| `write_file` | path under `~/…` | path under `/etc/…` | — |
| `patch` (replace) | replace under `~/…` (harness seeds file with `"a"` first) | replace under `/etc/…` | — |
| `patch` (V4A mixed) | — | Update `~/…` + Delete `/etc/…` (fail-closed batch) | Update `~/…` + Delete `~/…` (per-intent AE/Guardian; batch fails if any op BLOCKs) |
| `cronjob` (generic) | — | — | live only: `action: list` (no gateway LLM E2E) |

Multi-intent `patch` calls map to multiple IntentFrame `/validate` requests inside the adapter;
the plugin still sees one allow/block for the single Hermes tool call.

### Probe harness determinism

E2E probes use explicit LLM prompts to validate the **gateway → plugin → adapter →
IntentFrame** chain, not open-ended agent behavior. Harness setup (not policy weakening):

| Mechanism | Where | Why |
|-----------|-------|-----|
| **`seed_patch_replace_target()`** | `tests/hermes_tool_probes.py`; called from `run_patch_replace_allow_with_retries` | `patch replace` requires an existing file with `old_string`; harness writes `"a"` before each attempt |
| **Pass-unique markers** | `_pass_marker_slug()` in `test_gateway_e2e.py` → suffix `-p1`, `-p2a`, `-p2b` | Pass 2a reuses Pass 1 sandbox; unique markers avoid overwrite BLOCK on stale files |
| **Explicit block prompts** | `run_write_file_block_once`, `run_patch_replace_block_once`, `run_patch_v4a_mixed_block_once` in `api_client.py` | Keep `/etc/…`, `sudo`, and V4A delete paths verbatim; one tool call; no rewrite to `~/` or `/tmp` |

Block assertions still require blocked tool output and the expected path/command shape.
Allow assertions still fail on blocked output.

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
2. One or more intent evaluations per governed tool call (multi-intent `patch` emits several)

With the default all-governed yaml, a full pass runs many probes (terminal,
write_file, patch replace + block + V4A semantic + V4A block), so expect **multiple**
intent blocks in `intentframe-server.log` — not a fixed count of four.

If the LLM fails before emitting a tool `function_call`, **IntentFrame logs may be empty**
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
| `patch replace ALLOW` fails Pass 2a (overwrite BLOCK) | Same marker/file reused across passes | Pass-unique marker + `seed_patch_replace_target` (see [Probe harness determinism](#probe-harness-determinism)) |
| `patch replace BLOCK`: path under `/tmp/…` | LLM rewrote `/etc/…` after block | Explicit block prompt in `run_patch_replace_block_once` |
| Toolsets probe: `cronjob missing from get_tool_definitions()` | Probe subprocess lacks gateway session env | Toolsets live sets `HERMES_GATEWAY_SESSION=1` in probe env; see [Recent fixes](#recent-fixes-2026-06) under toolsets section |

## Related docs

- [`docs/hermes-intentframe-state-report.md`](../../docs/hermes-intentframe-state-report.md) — current integration snapshot
- [`docs/hermes-intentframe-integration-guide.md`](../../docs/hermes-intentframe-integration-guide.md) — integrate, add tools, testing pyramid
- [`docs/hermes-plugin-registration-order.md`](../../docs/hermes-plugin-registration-order.md) — gateway preload + load order
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
uv run --package intentframe-integrations-cli python tests/hermes_gateway/test_provider_request_contract.py
uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_scoped_governance_yaml.py
```

`test_scoped_governance_yaml.py` includes `assert_governance_env_contract` (env
parity with CLI child env builders). `test_hermes_install.py` covers
`build_gateway_env`, `_adapter_env`, and `format_env_exports` override behavior.

## Toolsets + provider payload test (opt-in, networked LLM)

Lighter-weight than full gateway E2E: proves intentframe-gate changes appear on the
**OpenAI upstream `tools=` payload**, not just Hermes config/listing surfaces.
Covers **all** governed catalog tools (including generic mappers like `cronjob`), not
only the native-mapper subset used for gateway E2E ALLOW/BLOCK probes.

Entrypoint: `test_gateway_toolsets_live.py`  
Wrapper: `tests/scripts/test-hermes-gateway-toolsets.sh`

Requires `OPENAI_API_KEY`.

### Flow

```
GET /v1/toolsets     →  api_server tool name surface (~31 names)
schema probe         →  registry schemas (governed + reason_required)
POST /v1/responses   →  real chat.completions round-trip + request dump
assertions           →  token usage > 0, governed tools + reason in tools=
```

Hermes gateway starts with `HERMES_DUMP_REQUESTS=1`. The schema probe subprocess
sets `HERMES_GATEWAY_SESSION=1` so ``cronjob`` passes Hermes ``check_fn`` (same
as the running gateway). One cheap `POST /v1/responses`
prompts the model to reply `OK` without calling tools (minimizes IntentFrame policy
noise; still sends the full `tools=` list upstream).

### Three surfaces (do not conflate)

| Surface | What it proves |
|---------|----------------|
| `GET /v1/toolsets` | Hermes **config** tool names for api_server (e.g. ~31) |
| `probe_hermes_tool_schemas.py` | **Registry** schemas for all governed tools (`reason` + gate), including generic mappers |
| Request dump + round-trip assert | **OpenAI `chat.completions` payload** — all governed tools with required `reason` in `tools=` |

The registry count and toolsets count differ by design — not every listed toolset
name becomes a registry definition on the LLM path. See
[`docs/hermes-intentframe-integration-guide.md`](../../docs/hermes-intentframe-integration-guide.md#two-different-tool-surfaces-do-not-conflate).

### Assertions

| Helper | Checks |
|--------|--------|
| `assert_gateway_openai_roundtrip()` | Gateway `status: completed` and `usage.total_tokens > 0` |
| `assert_provider_tools_surface()` | All governed catalog tools in dump `request.body.tools` with required `reason` |

The request dump is written at **preflight** (before the HTTP call to OpenAI). Token
usage from the gateway response proves the call **completed** — the dump alone only
proves Hermes **built** the payload.

Contract helpers: `tests/hermes_gateway/provider_request_contract.py`

### Stderr on success

1. **OpenAI round-trip proof** — run marker, input/output/total tokens, provider URL/model
2. **Provider tools= snapshot** — run marker, dump path, sorted tool list, `[governed, reason_required=true]` markers

### Finding the call in OpenAI Platform

Each run prints a unique marker: ``intentframe-toolsets-<run_id>``. Search Platform
Logs / Usage for that token in the user prompt or assistant reply to match this run.

Typical signature:

- User prompt contains: ``Reply with exactly this single token ... intentframe-toolsets-...``
- System includes: ``Automated IntentFrame toolsets integration test run_id=...``
- ~11k input tokens, **17+ tools** in the Tools list, output is the marker token
- No tool invocations (unlike full E2E entries that say “Call the terminal tool…”)

Platform Logs list tool **names** but not JSON schema details (`reason` in `required`).
Use the test’s provider dump assertion for schema proof.

```bash
RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh
```

The full gateway E2E also asserts `/v1/toolsets` before the LLM probes, but uses
tool-calling prompts for ALLOW/BLOCK — a different OpenAI log signature.

### Recent fixes (2026-06)

These were gaps between production behavior and what the toolsets live harness asserted.

| Bug | Symptom | Root cause | Fix |
|-----|---------|------------|-----|
| **Partial governed coverage** | Toolsets test skipped `cronjob` while production governs it | Probe and provider dump used `gateway_e2e_probe_tool_names()` (native E2E tier only) | Probe uses `governed_tool_names()`; live test asserts `template_governed_tool_names()` on the request dump |
| **Preload map drift** | Adding a governed builtin required editing a hardcoded Python dict | `GOVERNED_BUILTIN_MODULES` lived in `builtin_preload.py`, separate from `tools.yaml` | `builtin_module: tools.<module>` per tool in repo `tools.yaml`; plugin preload imports enabled specs; shared + plugin loaders validate `tools.` prefix |
| **`cronjob` schema probe failure** | Probe reported `cronjob missing from get_tool_definitions()` despite yaml preload | Preload registered `cronjob`, but Hermes `check_cronjob_requirements()` filters it unless `HERMES_GATEWAY_SESSION=1` (or interactive/exec env); probe subprocess lacked that env while the gateway had it | `_run_schema_probe()` sets `probe_env["HERMES_GATEWAY_SESSION"] = "1"` to mirror the running gateway |

Guarded by `test_governed_tool_coverage.py` (`test_toolsets_live_verifies_full_governed_catalog`) and loader parity in `tests/hermes_plugin/test_gate.py` (`builtin_module` must match between plugin and shared loaders).
