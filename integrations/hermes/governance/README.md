# Hermes governance artifacts

| File | Owner | Purpose |
|------|-------|---------|
| `tools.yaml` (repo) | **Dev** | Tool catalog: names, mappers, action IDs, default `enabled`, `builtin_module` (Hermes preload import path) |
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

## Derived artifacts (sync replacement)

There is **no** `intentframe-integrations sync hermes` command. Instead:

- **Source of truth:** repo `tools.yaml` (catalog, mappers, action IDs).
- **Dev updates shipped files by hand** when adding a tool (see workflow below).
- **CI guard:** `tests/intentframe_integrations/test_actions_manifest.py` fails if
  `generic_actions.manifest`, `agent.json`, or `executor.yaml` drift from the catalog.
- **Runtime:** `integrate hermes` / `start hermes` only **copy** committed templates to
  `~/.intentframe/...` on first use — they never regenerate derived lists from yaml.

This replaces a codegen/sync CLI: manual edits preserve policy comments and formatting;
the golden test catches drift instead of auto-rewriting repo files.

Verify after edits:

```bash
uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_actions_manifest.py
uv run --package intentframe-integrations-cli python tests/hermes_plugin/test_gate.py
uv run --package intentframe-integrations-cli python tests/hermes_plugin/test_builtin_preload.py
uv run --package intentframe-integrations-cli python integrations/hermes/shared/tests/test_governance.py
```

### `builtin_module` (preload map)

Each governed Hermes builtin declares `builtin_module: tools.<module>` in repo
`tools.yaml`. The intentframe-gate plugin imports unique modules for **enabled**
tools before registry snapshot (see `builtin_preload.py`). Values must start with
`tools.` — validated by both plugin and shared loaders.

**Why yaml, not Python:** a hardcoded preload dict drifted from the catalog (e.g.
`cronjob` governed in yaml but easy to omit from code). Yaml is the single source;
`test_plugin_loader_matches_shared_template` asserts plugin/shared parity including
`builtin_module`.

**`cronjob` nuance:** preload registers the tool, but Hermes `get_tool_definitions()`
also applies `check_cronjob_requirements()` — requires `HERMES_GATEWAY_SESSION=1`
(or interactive/exec env). The toolsets schema probe sets session env to mirror the
gateway; see `tests/hermes_gateway/README.md` (Recent fixes).

**Outbound messaging:** Hermes does not expose `send_message` to the LLM by default;
proactive Slack/email/WhatsApp/SMS usually goes through governed **`terminal`**
(`hermes send …`) or **`cronjob`** (`deliver=`). See
[`docs/hermes-outbound-messaging-and-cronjob-governance.md`](../../../docs/hermes-outbound-messaging-and-cronjob-governance.md).

## Dev workflow (adding a generic tool)

1. Add entry to `tools.yaml` with `mapper: generic`, a `HERMES_*` action ID, and
   `builtin_module: tools.<module>` when Hermes registers the tool at import time.
2. Regenerate committed `generic_actions.manifest` to include the new action ID
   (golden test `tests/intentframe_integrations/test_actions_manifest.py` enforces parity).
3. Update `agent.json` `action_types`, shipped `policy.yaml`, and `executor.yaml`
   `supported_actions` (hand-edited; same golden test checks coverage).
4. Add live adapter + plugin semantic smoke probe in `tests/hermes_adapter/test_live.py`
   and `tests/hermes_plugin/test_bridge_gate_live.py` (no gateway LLM E2E).
5. Set `IF_DYNAMIC_BUNDLE_MANIFEST` in `agent.json` env (already points at runtime path).

Runtime automation never rewrites repo templates or user governance/policy files.
See [Derived artifacts (sync replacement)](#derived-artifacts-sync-replacement) above.
