# Hermes governance artifacts

| File | Owner | Purpose |
|------|-------|---------|
| `tools.yaml` (repo) | **Dev** | Tool catalog: names, mappers, action IDs, default `enabled` |
| `tools.yaml` (runtime) | **User** | Same catalog; user toggles `enabled` via `governance enable\|disable` |
| `generic_actions.manifest` (repo) | **Dev** | Static list of all `mapper: generic` action IDs (full catalog superset) |
| `generic_actions.manifest` (runtime) | **Copied once** | Seeded on `integrate hermes`; never overwritten by automation |

## User-facing CLI (runtime only)

- **`governance enable|disable hermes <tool>`** — flips `enabled` in runtime `tools.yaml`.
  Restart **Hermes gateway + adapter** (governance is loaded at process start).
  Does not touch manifest, policy, or repo files.
- **`policy set|reload|reset hermes`** — edits runtime `policy.yaml` and loads into
  policy-registry immediately. **No** gateway or backend restart needed.
  CLI applies `agent.json` env (including `IF_DYNAMIC_BUNDLE_MANIFEST`) via
  `load_and_activate_pack` before validating policy against registered bundles.

Governance and policy are **independent**: disabling a tool stops Hermes from sending
intents; policy rows for that action ID can remain without harm.

## Dev workflow (adding a generic tool)

1. Add entry to `tools.yaml` with `mapper: generic` and a `HERMES_*` action ID.
2. Regenerate committed `generic_actions.manifest` to include the new action ID
   (golden test `tests/intentframe_integrations/test_actions_manifest.py` enforces parity).
3. Update `agent.json` `action_types`, shipped `policy.yaml`, and `executor.yaml`
   `supported_actions` (hand-edited; same golden test checks coverage).
4. Add live adapter + plugin semantic smoke probe in `tests/hermes_adapter/test_live.py`
   and `tests/hermes_plugin/test_bridge_gate_live.py` (no gateway LLM E2E).
5. Set `IF_DYNAMIC_BUNDLE_MANIFEST` in `agent.json` env (already points at runtime path).

There is **no** user-facing `sync` command. Runtime automation never rewrites repo
templates or user governance/policy files.
