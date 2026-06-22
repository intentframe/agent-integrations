# intentframe-gate (Hermes plugin)

Selective IntentFrame validate-only gate for governed Hermes tools.

## Governed tools (v1)

Configured in `integrations/hermes/governance/tools.yaml`:

- `terminal`, `process` → `RUN_COMMAND`
- `write_file`, `patch` (update/add) → `WRITE_HOST_FILE`
- `delete_file`, `patch` (V4A delete) → `DELETE_HOST_FILE`

Reads and helpers stay ungoverned unless added to the contract explicitly.

## Architecture

For each governed tool:

1. Schema injects required `reason` (layer 1)
2. Handler validates via adapter before delegating to Hermes (layer 2)
3. Adapter maps tool args to IntentFrame action(s) and calls the bridge

`registry.register` is hooked so MCP refresh cannot silently reinstall unwrapped handlers.

## Env

- `IF_AGENT_ADAPTER_SOCKET` — path to Hermes adapter UDS (required)
- `HERMES_GOVERNANCE_YAML` — optional override for governed-tools contract

## Enable

```yaml
plugins:
  enabled:
    - intentframe-gate
```
