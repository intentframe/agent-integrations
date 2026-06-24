# intentframe-gate (Hermes plugin)

Selective IntentFrame validate-only gate for **governed** Hermes tools.

**Deep dive (June 2026 session):** [`docs/hermes-governance-execute-code-and-schema-hooks.md`](../../../docs/hermes-governance-execute-code-and-schema-hooks.md) — `execute_code` governance, schema hook architecture, `read_terminal` lessons, what we did **not** do.

## What “governed” means

A tool is **governed** when it appears in `governance/tools.yaml` with
`enabled: true`. The plugin then:

1. Injects required `reason` into the final model-facing tool schema
2. Validates via adapter before delegating to Hermes

`enabled: false` (or absent from the runtime governed set) means Hermes runs the
**native handler without IntentFrame gate**. That is separate from whether Hermes
exposes the tool on `/v1/toolsets`.

Full terminology: [`docs/agent-tool-gating.md`](../../../docs/agent-tool-gating.md#terminology-what-governed-means).
Integration guide: [`docs/hermes-intentframe-integration-guide.md`](../../../docs/hermes-intentframe-integration-guide.md).
Gateway startup / preload: [`docs/hermes-plugin-registration-order.md`](../../../docs/hermes-plugin-registration-order.md).

## Governed tools (v1)

Configured in `integrations/hermes/governance/tools.yaml` (runtime copy under
`~/.intentframe/integrations/hermes/governance/tools.yaml`):

- `terminal` → `RUN_COMMAND`
- `execute_code` → `RUN_COMMAND` (Python encoded as `python -c …` for `command_shield`)
- `write_file`, `patch` (update/add) → `WRITE_HOST_FILE`
- `patch` (V4A delete) → `DELETE_HOST_FILE`
- `cronjob` → `HERMES_CRONJOB` (generic mapper)

Reads and helpers stay ungoverned unless added to the contract explicitly.

## Architecture

Two independent layers per governed tool:

| Layer | When | What |
|-------|------|------|
| **Schema** | `registry.get_definitions` (+ `build_execute_code_schema` for dynamic rebuild) | Model sees required `reason` |
| **Execution** | Snapshot wrap + `registry.register` hook | Validate, strip `reason`, delegate to Hermes |

At plugin load (`register()`):

1. `install_registry_hook()` — wrap handlers on future `registry.register`; inject `reason` on `registry.get_definitions`
2. `preload_governed_builtins(governed)` — selective Hermes module import from yaml `builtin_module`
3. `install_execute_code_schema_hook()` — `reason` after Hermes dynamic `execute_code` schema rebuild
4. Snapshot loop — wrap governed handlers with `override=True` (schema stays `entry.schema`; finalization is on get_definitions path)

### Critical: never `import model_tools` during `register()`

Hermes runs `discover_builtin_tools()` at `model_tools` import time, which registers
extras like desktop-only `read_terminal` into the `terminal` toolset. That breaks
the pinned `GET /v1/toolsets` contract (`['process', 'terminal']` only).

We **rejected** wrapping `model_tools.get_tool_definitions` at plugin load for this reason.
Schema finalization uses registry composition hooks instead. See the deep-dive doc above.

On gateway startup, plugins load **before** Hermes builtins. [`builtin_preload.py`](builtin_preload.py)
imports ``builtin_module`` from each **enabled** governed tool only — not full
``discover_builtin_tools()``.

When adding a governed Hermes builtin:

1. Set ``builtin_module: tools.<module>`` in the repo catalog template.
2. Extend [`tests/hermes_plugin/test_builtin_preload.py`](../../../tests/hermes_plugin/test_builtin_preload.py).
3. If Hermes rebuilds the tool schema after `get_definitions` (like `execute_code`), add a builder hook — do not rely on `get_definitions` alone.

## Env

- `IF_AGENT_ADAPTER_SOCKET` — path to Hermes adapter UDS (required)
- `HERMES_GOVERNANCE_YAML` — optional override for governance yaml (runtime governed set)

The Hermes gateway process and adapter sidecar inherit these from the CLI parent
environment. If `HERMES_GOVERNANCE_YAML` is already set when you run
`intentframe-integrations start hermes` or `gateway start hermes`, that value is
preserved (the CLI does not overwrite it with the sandbox default from
`agent.json`). `integrate hermes` prints the effective export lines for manual shells.

## Enable the plugin

```yaml
plugins:
  enabled:
    - intentframe-gate
```

This loads the plugin; per-tool governance is controlled in `governance/tools.yaml`.

## Verification

```bash
# Unit — includes test_install_registry_hook_does_not_import_model_tools
.venv/bin/python tests/hermes_plugin/test_registry_hook.py

# Live — toolsets + schema probe + OpenAI tools= payload
RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh
```
