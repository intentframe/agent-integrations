# TODO: Hermes-specific IntentFrame action bundles (patch / write)

## Problem

Hermes `patch` and `write_file` map to native IntentFrame actions (`WRITE_HOST_FILE`,
`DELETE_HOST_FILE`) via the adapter mapper. That keeps deterministic path constraints
working, but AE and Guardian see **generic file-write semantics**, not Hermes tool semantics.

Patch replace is especially brittle. The mapper synthesizes write content like:

```text
--- ~/path
-old
+new
(replace 'a')
```

Native `HostFilesActionBundle` supplies AE prompt `critical_write_file` and **no**
bundle-specific Guardian prompt (fallback default). Guardian then treats benign probes as:

- **File missing:** “claims replace but destination does not exist → data deception”
- **File exists:** “irreversible overwrite / unspecified live patch content → hidden behavior”

Same args can ALLOW on one validate call and BLOCK on the next. Live tests use semantic
smoke for patch replace; gateway E2E uses seed + 3× retries for strict ALLOW.

Refs: `docs/delete-host-file-validation.md`, `tests/hermes_gateway/README.md#probe-harness-determinism`,
`~/.intentframe/logs/guardian_outputs.log` (search `intentframe-e2e-patch-live`).

## Short-term (done / acceptable)

- Live adapter + plugin gate: `test_patch_replace_allow_semantic` — valid ALLOW or BLOCK shape
- Gateway E2E: strict patch replace ALLOW with `seed_patch_replace_target` + retries
- Plain `write_file` ALLOW remains strict (maps cleanly to create-under-`~/`)

## Long-term fix: custom action bundle(s)

IntentFrame bundle SDK supports per-action hooks including `build_ai_context()` with
`ae_system_instructions`, `guardian_system_instructions`, and trusted external context.
See `intentframe_bundle_sdk.types.BundleAIContext` and pipeline UNDECIDED path in
`intentframe-server` (AE → Guardian).

**Do not** register a second bundle for `WRITE_HOST_FILE` — the registry rejects
duplicate `action_id`s. Introduce **Hermes-specific action types** and a dedicated bundle.

### Proposed direction

1. **New action types** (names TBD), e.g.:
   - `HERMES_WRITE_FILE` — direct `write_file` tool
   - `HERMES_PATCH_REPLACE` — patch `mode: replace`
   - `HERMES_PATCH_APPLY` — patch V4A multi-op (or split write vs delete sub-intents)

2. **`HermesHostFilesActionBundle`** (or split bundles) registered at runtime startup:
   - Reuse / delegate deterministic gates from native host files (`allowed_host_paths`, deny floor)
   - Custom AE + Guardian prompts that explain:
     - replace mode: `old_string` / `new_string` are expected semantics, not deception
     - overwrite of an existing file under `~/` is normal for patch replace
     - V4A batch context (`patch_operations` manifest) when present
   - Optional: deterministic ALLOW fast-path for probe-shaped home writes (policy-gated)

3. **Adapter mapper** maps Hermes tools → new action types instead of `WRITE_HOST_FILE` /
   `DELETE_HOST_FILE` for governed validate paths (executor still validate-only).

4. **Policy** (`integrations/hermes/policy.yaml` + runtime copy):
   - `allowed_actions` lists new action types
   - Constraints mirror current `WRITE_HOST_FILE` / `DELETE_HOST_FILE` host path rules

5. **`agent.json`** `action_types` updated to match seeded policy.

6. **Tests**
   - Restore strict ALLOW for live patch replace (no semantic-only workaround)
   - Reduce or remove gateway patch-replace retry dependence once decisions stabilize
   - Unit tests for bundle `build_ai_context` + mapper → intent shape

### Registration / packaging

- Bundle lives in this repo (e.g. `integrations/hermes/bundle/` or `shared/`) and loads
  via IntentFrame bundle entry point alongside native-kit, **or** extends native-kit if
  upstream accepts Hermes-specific bundle in a separate package.
- Confirm how `if-integration-backend` / supervisor profile loads bundle plugins for
  the integrations runtime (see `docs/NATIVE_KIT_INTEGRATION.md`).

### Open questions

- One bundle vs separate bundles per action type?
- Keep `DELETE_HOST_FILE` for V4A deletes or add `HERMES_PATCH_DELETE`?
- Should patch replace skip generic file-intel pre-pipeline or feed structured patch metadata?
- Upstream IntentFrame: contribute prompts to native-kit vs Hermes-only bundle in agent-integrations?

## Related code

| Area | Path |
|------|------|
| Hermes → intent mapping | `integrations/hermes/adapter/src/hermes_adapter/mapper.py` |
| Native host files bundle | `intentframe-native-kit/.../actions/host_files/bundle.py` |
| Generic write AE prompt | `intentframe-native-kit/.../shared/files/prompts_ae.py` |
| Bundle SDK hooks | `intentframe-bundle-sdk/action.py`, `types.py` |
| Live semantic workaround | `tests/hermes_adapter/test_live.py`, `tests/hermes_plugin/test_bridge_gate_live.py` |
| Gateway retries | `tests/hermes_gateway/api_client.py` (`run_patch_replace_allow_with_retries`) |

## Success criteria

- Patch replace ALLOW under `~/` with seeded probe file is **deterministic** (or stable
  without 3× retries) in live adapter/gate tests.
- Guardian block reasons no longer cite spurious “data deception” / “unspecified live patch”
  for documented Hermes patch replace probes.
- Security unchanged: `/etc/…`, deny-floor paths, and V4A system deletes still BLOCK deterministically.
