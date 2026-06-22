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

## Governed tools (v1)

Configured in `integrations/hermes/governance/tools.yaml` (runtime copy under
`~/.intentframe/integrations/hermes/governance/tools.yaml`):

- `terminal`, `process` → `RUN_COMMAND`
- `write_file`, `patch` (update/add) → `WRITE_HOST_FILE`
- `delete_file`, `patch` (V4A delete) → `DELETE_HOST_FILE`

Reads and helpers stay ungoverned unless added to the contract explicitly.

## Architecture

For each **governed** tool:

1. Schema injects required `reason` (layer 1)
2. Handler validates via adapter before delegating to Hermes (layer 2)
3. Adapter maps tool args to IntentFrame action(s) and calls the bridge

`registry.register` is hooked so MCP refresh cannot silently reinstall unwrapped handlers.

## Env

- `IF_AGENT_ADAPTER_SOCKET` — path to Hermes adapter UDS (required)
- `HERMES_GOVERNANCE_YAML` — optional override for governance yaml (runtime governed set)

## Enable the plugin

```yaml
plugins:
  enabled:
    - intentframe-gate
```

This loads the plugin; per-tool governance is controlled in `governance/tools.yaml`.
