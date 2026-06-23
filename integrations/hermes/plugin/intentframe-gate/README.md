# intentframe-gate (Hermes plugin)

Selective IntentFrame validate-only gate for **governed** Hermes tools.

## What “governed” means

A tool is **governed** when it appears in `governance/tools.yaml` with
`enabled: true`. The plugin then:

1. Injects required `reason` into the tool schema
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

- `terminal`, `process` → `RUN_COMMAND`
- `write_file`, `patch` (update/add) → `WRITE_HOST_FILE`
- `patch` (V4A delete) → `DELETE_HOST_FILE`

Reads and helpers stay ungoverned unless added to the contract explicitly.

## Architecture

For each **governed** tool:

1. Schema injects required `reason` (layer 1)
2. Handler validates via adapter before delegating to Hermes (layer 2)
3. Adapter maps tool args to IntentFrame action(s) and calls the bridge

At plugin load (`register()`):

1. `install_registry_hook()` — gate future `registry.register` (MCP refresh)
2. `preload_governed_builtins(governed)` — selective Hermes module import
3. Snapshot loop — wrap governed registry entries with `override=True`

On gateway startup, plugins load **before** Hermes builtins. [`builtin_preload.py`](builtin_preload.py)
imports ``builtin_module`` from each **enabled** governed tool in the dev-owned
``governance/tools.yaml`` so the snapshot loop can wrap them without calling full
``discover_builtin_tools()`` (which would pull in extras like ``read_terminal``).
Details: [`docs/hermes-plugin-registration-order.md`](../../../docs/hermes-plugin-registration-order.md).

When adding a governed Hermes builtin, set ``builtin_module: tools.<module>`` in the
repo template and extend
[`tests/hermes_plugin/test_builtin_preload.py`](../../../tests/hermes_plugin/test_builtin_preload.py).

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
