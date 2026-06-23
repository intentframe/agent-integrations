# IntentFrame × Hermes integration — state report

> Snapshot of the Hermes agent integration as of **2026-06-23**. For how-to and
> troubleshooting, see [`hermes-intentframe-integration-guide.md`](./hermes-intentframe-integration-guide.md).

---

## Executive summary

| Area | Status |
|------|--------|
| Governed tool catalog | **4 tools**: `terminal`, `process`, `write_file`, `patch` |
| Standalone `delete_file` Hermes tool | **Removed** — delete via `patch` V4A `*** Delete File:` → `DELETE_HOST_FILE` |
| Plugin gateway registration | **Fixed** — selective `builtin_preload` before registry snapshot |
| Full gateway E2E (pass 1, 2a, 2b) | **Green** — all four governed tools, probes typically attempt 1 |
| Hermes version tested | **0.17.0** |

The integration is production-shaped: CLI install → start → integrate → gateway, with
IntentFrame validate-only gating on governed tool names. E2E validates the full chain
(gateway → plugin → adapter → bridge → policy), not open-ended agent behavior.

---

## Architecture

```
LLM (POST /v1/responses)
  → Hermes gateway (intentframe-gate plugin)
  → POST adapter.sock /validate-tool
  → hermes-adapter (mapper.py)
  → POST bridge.sock /validate
  → IntentFrame (policy-registry, AE, Guardian, executor validate_only)
  → ALLOW → native Hermes handler runs locally
  → BLOCK → JSON error, no side effect
```

### Key environment variables

| Variable | Role |
|----------|------|
| `IF_AGENT_ADAPTER_SOCKET` | Path to Hermes adapter UDS |
| `HERMES_GOVERNANCE_YAML` | Runtime governed-tool set (shell export overrides `agent.json` default) |

### Repository layout

| Path | Purpose |
|------|---------|
| `integrations/hermes/governance/tools.yaml` | Default governed-tool **template** (4 entries) |
| `integrations/hermes/policy.yaml` | RUN_COMMAND + host-file + deletion rules |
| `integrations/hermes/agent.json` | Agent profile, action types, exported env |
| `integrations/hermes/adapter/` | Sidecar: map tool args → IntentFrame `/validate` |
| `integrations/hermes/plugin/intentframe-gate/` | Plugin: `reason` injection + gate + preload |
| `intentframe-integrations-cli/` | `install`, `start`, `integrate`, `gateway`, `doctor` |

---

## Governed tools (v1 catalog)

Configured in runtime `~/.intentframe/integrations/hermes/governance/tools.yaml`
(seeded from repo template on first `integrate hermes`). **`enabled: true`** means
IntentFrame gate active; **`enabled: false`** means native Hermes handler without gate.

| Hermes tool | IntentFrame action(s) | Mapper kind | Notes |
|-------------|----------------------|-------------|-------|
| `terminal` | `RUN_COMMAND` | `terminal` | `terminal_json` blocked shape |
| `process` | `RUN_COMMAND` | `process` | Maps `action: run` + `data` to shell command |
| `write_file` | `WRITE_HOST_FILE` | `write_file` | Path + content |
| `patch` | `WRITE_HOST_FILE`, `DELETE_HOST_FILE` | `patch` | Replace mode + V4A multi-intent |

**Not governed by default:** `read_file`, `search_files`, browser tools, skills, etc.
They may still appear on `GET /v1/toolsets` and run without IntentFrame validation.

**Delete coverage:** There is no separate Hermes `delete_file` tool name. Host deletes
are expressed as V4A `*** Delete File:` operations inside `patch`; the adapter maps
each delete op to `DELETE_HOST_FILE`.

---

## Plugin (`intentframe-gate`)

Hermes gateway calls `discover_plugins()` **before** builtin tool modules import.
Without preload, the plugin’s registry snapshot can be empty and governed tools never
reach the OpenAI **Tools** parameter (even when `/v1/toolsets` lists them).

At `register()`:

1. **`install_registry_hook()`** — wrap tools registered later (e.g. MCP refresh).
2. **`preload_governed_builtins(governed)`** — selective import from
   `GOVERNED_BUILTIN_MODULES` in [`builtin_preload.py`](../integrations/hermes/plugin/intentframe-gate/builtin_preload.py):
   - `terminal` → `tools.terminal_tool`
   - `process` → `tools.process_registry`
   - `write_file`, `patch` → `tools.file_tools`
3. **Snapshot loop** — wrap governed entries with `inject_reason()` + `gate_tool_call()`.

See [`hermes-plugin-registration-order.md`](./hermes-plugin-registration-order.md) for
load-order evidence and bisect notes.

---

## Adapter

- Maps Hermes tool arguments to IntentFrame validate payloads (including required `reason`).
- **Multi-intent `patch`:** one V4A blob → multiple intents; adapter **fail-closes** on first BLOCK.
- Per-op write `content` and batch metadata (`patch_op_index`, `patch_op_count`, …) so
  AE/Guardian judge each intent honestly.

---

## CLI workflow (validated by E2E)

```bash
bin/intentframe-integrations install hermes
bin/intentframe-integrations start hermes
bin/intentframe-integrations integrate hermes
bin/intentframe-integrations doctor hermes
bin/intentframe-integrations gateway start hermes --api-server
```

`integrate hermes` symlinks the plugin, enables it in `$HERMES_HOME/config.yaml`, syncs
adapter venv, and seeds runtime governance yaml if missing.

---

## Test pyramid

| Layer | Entry | LLM / network |
|-------|-------|---------------|
| Unit | `tests/hermes_plugin/`, `tests/hermes_gateway/test_*.py`, adapter tests | No |
| Toolsets | `RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh` | Hermes install only |
| Live integration | `./tests/scripts/test-hermes-integration.sh` | Backend; no LLM probes |
| Gateway E2E | `RUN_HERMES_GATEWAY_E2E=1 ./tests/scripts/test-hermes-gateway-e2e.sh` | OpenAI + full stack |

### Gateway E2E passes

| Pass | Scenario |
|------|----------|
| **1** | Greenfield install journey |
| **2a** | Idempotent install/integrate on same sandbox |
| **2b** | External `HERMES_BIN` symlink, first-time integrate |

With default temp governance yaml, each pass runs ALLOW/BLOCK/semantic probes for all
four catalog tools.

### E2E harness determinism (2026-06)

Recent harness fixes separate **test setup** from **policy behavior**:

| Mechanism | Purpose |
|-----------|---------|
| `seed_patch_replace_target()` | Before `patch replace ALLOW`, write target file with content `"a"` |
| Pass-unique markers (`-p1`, `-p2a`, `-p2b`) | Avoid Pass 2a reusing Pass 1 filesystem state |
| Explicit block prompts | Keep `/etc/…` paths and V4A delete paths verbatim; one tool call; no sandbox rewrite |

Assertions still require real ALLOW (non-blocked output) or BLOCK (`/etc/` + blocked JSON).
See [`tests/hermes_gateway/README.md`](../tests/hermes_gateway/README.md).

---

## Recent changes (branch `fix-plugin-new-mechanism`)

| Change | Rationale |
|--------|-----------|
| `builtin_preload` + registry snapshot order | Fix missing `terminal`/`process` in OpenAI Tools |
| Remove invented `delete_file` catalog entry | Hermes 0.17 has no standalone delete tool; use `patch` V4A |
| Patch replace seed + pass markers | Fix flaky ALLOW and Pass 2a overwrite BLOCK |
| Hardened block probe prompts | Fix LLM rewriting `/etc/` to sandbox paths |

---

## Known limitations

1. **E2E uses explicit LLM prompts** — validates gate chain, not vague user instructions.
2. **Assertions use last tool call** in response (`calls[-1]`); block prompts discourage multi-call retries.
3. **V4A home delete semantic probe** accepts ALLOW or BLOCK (Guardian decision).
4. **`/v1/toolsets`** exposes many native Hermes tools; only catalog tools are governed by default.
5. **Upstream ideal:** Hermes could discover builtins before plugins; until then, plugin owns preload.

---

## References

| Topic | Doc / code |
|-------|------------|
| Integration guide | [`hermes-intentframe-integration-guide.md`](./hermes-intentframe-integration-guide.md) |
| Plugin load order | [`hermes-plugin-registration-order.md`](./hermes-plugin-registration-order.md) |
| Gating terminology | [`agent-tool-gating.md`](./agent-tool-gating.md) |
| Native-kit alignment | [`NATIVE_KIT_INTEGRATION.md`](./NATIVE_KIT_INTEGRATION.md) |
| DELETE_HOST_FILE validation | [`delete-host-file-validation.md`](./delete-host-file-validation.md) |
| Hermes README | [`integrations/hermes/README.md`](../integrations/hermes/README.md) |
| E2E harness | [`tests/hermes_gateway/README.md`](../tests/hermes_gateway/README.md) |
