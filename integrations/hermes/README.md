# Hermes integration

Hermes does **not** ship an IntentFrame executor pack or runtime. This folder provides:

| Path | Purpose |
|------|---------|
| `agent.json` | Agent profile, adapter socket, exported `env` for Hermes plugin |
| `policy.yaml` | Shipped policy **template** (copied to runtime on first integrate/start) |
| `governance/tools.yaml` | Default governed-tool **template** (seeded to runtime on first integrate) |
| `governance/actions.manifest` | Static generic action IDs (copied to runtime on first integrate) |
| `governance/README.md` | Dev vs user ownership for governance artifacts |
| `shared/` | `hermes-governance` package — contract loader for adapter |
| `adapter/` | Hermes adapter sidecar (bridge client, tool mapping, HTTP/UDS server) |
| `plugin/intentframe-gate/` | Hermes plugin — selective schema override + adapter gate |

Docs: [`docs/agent-tool-gating.md`](../../docs/agent-tool-gating.md),
[`docs/hermes-intentframe-integration-guide.md`](../../docs/hermes-intentframe-integration-guide.md)
(integrate, add/change tools, testing),
[`docs/hermes-intentframe-state-report.md`](../../docs/hermes-intentframe-state-report.md)
(current snapshot),
[`docs/hermes-plugin-registration-order.md`](../../docs/hermes-plugin-registration-order.md)
(gateway preload + snapshot),
[`docs/NATIVE_KIT_INTEGRATION.md`](../../docs/NATIVE_KIT_INTEGRATION.md)
(native-kit bundle, adding governed tools).

## Quick start

From the **repo root**:

```bash
uv sync --all-packages
export OPENAI_API_KEY=sk-...

bin/intentframe-integrations install hermes
bin/intentframe-integrations run hermes
```

Or step by step:

```bash
bin/intentframe-integrations install hermes
bin/intentframe-integrations start hermes
bin/intentframe-integrations integrate hermes
bin/intentframe-integrations doctor hermes
bin/intentframe-integrations gateway start hermes --api-server
```

## Governed tools (v1)

**Governed** = IntentFrame validate-only gate is active for a Hermes tool name
(plugin wrap + adapter validate). It is **not** “Hermes enabled the tool on
`/v1/toolsets`.” Ungoverned tools may still appear there and run without the gate.

Terminology: [`docs/agent-tool-gating.md`](../../docs/agent-tool-gating.md#terminology-what-governed-means).

Configured in runtime `~/.intentframe/integrations/hermes/governance/tools.yaml`
(seeded from repo `governance/tools.yaml` on first integrate). Each entry has
`enabled: true|false` — read **`enabled` as IntentFrame-governed**:

| Hermes tool | IntentFrame action | `enabled: false` effect |
|-------------|-------------------|-------------------------|
| `terminal`, `process` | `RUN_COMMAND` | Native Hermes handler, no IF gate |
| `write_file`, `patch` (update/add) | `WRITE_HOST_FILE` | same |
| `patch` (V4A delete) | `DELETE_HOST_FILE` | same |
| `cronjob` | `HERMES_CRONJOB` | same (semantic-only via dynamic bundle) |

```bash
bin/intentframe-integrations governance list hermes
bin/intentframe-integrations governance disable hermes write_file
bin/intentframe-integrations governance enable hermes write_file
```

**Restart Hermes gateway + adapter** after enable/disable (governance is cached at
process start). IntentFrame backend does **not** need restart for governance toggles.

Governance and policy are **independent gates** — they do not need to stay in sync.
Disabling a tool stops Hermes from sending intents; manifest and policy rows for that
action ID can remain harmlessly. See [`governance/README.md`](governance/README.md).

## Policy (runtime)

IntentFrame policy rules live at `~/.intentframe/integrations/hermes/policy.yaml`
(copied from shipped `policy.yaml` on first `integrate` or `start`). Edit that file,
then reload into the running registry:

```bash
bin/intentframe-integrations policy show hermes
vim ~/.intentframe/integrations/hermes/policy.yaml
bin/intentframe-integrations policy reload hermes

# Install an external policy file (copy + load)
bin/intentframe-integrations policy set hermes ~/my-hermes-policy.yaml

# Restore shipped default (copy + load)
bin/intentframe-integrations policy reset hermes
# or: integrate hermes --reset-policy
```

Policy changes apply immediately — no gateway or adapter restart needed.
`start hermes` seeds from the **runtime** policy file, not the repo copy.

## Commands

```bash
bin/intentframe-integrations install hermes [--version VERSION] [--force]
bin/intentframe-integrations start hermes
bin/intentframe-integrations integrate hermes [--copy] [--skip-config] [--reset-governance] [--reset-policy]
bin/intentframe-integrations doctor hermes [--install-only]
bin/intentframe-integrations gateway start hermes [--api-server]
bin/intentframe-integrations gateway stop hermes
bin/intentframe-integrations run hermes
bin/intentframe-integrations stop
```

`integrate hermes` symlinks the plugin to `$HERMES_HOME/plugins/intentframe-gate`, merges
`plugins.enabled` in `$HERMES_HOME/config.yaml`, syncs the adapter venv at
`~/.intentframe/integrations/hermes/.venv`, and on first use copies runtime artifacts
from repo templates (never overwrites existing user files):

- `~/.intentframe/integrations/hermes/governance/tools.yaml`
- `~/.intentframe/integrations/hermes/governance/actions.manifest`
- `~/.intentframe/integrations/hermes/policy.yaml`

### Config ownership

| What | Who edits | Restart after change |
|------|-----------|----------------------|
| Runtime `governance/tools.yaml` `enabled` | User (`governance enable\|disable`) | Hermes gateway + adapter |
| Runtime `policy.yaml` | User (`policy set\|reload\|reset`) | None (live registry) |
| Repo templates (`tools.yaml`, `actions.manifest`, `policy.yaml`, `agent.json`, `executor.yaml`) | Dev only | Backend restart if manifest/action IDs change |

There is no user-facing `sync` command. Runtime CLI never rewrites repo templates.

### Governance env contract

`agent.json` declares a default `HERMES_GOVERNANCE_YAML` (runtime sandbox path above).
The CLI propagates governance config to child processes as follows:

| Step | Behavior |
|------|----------|
| `integrate hermes` | Prints `export …` using the **effective** value (`os.environ` overrides `agent.json`). Copies governance yaml, actions manifest, and policy template to runtime on first use. |
| `start hermes` (adapter) | `_adapter_env()` copies the parent environment and `setdefault`s `pack.agent.env` keys — an existing `HERMES_GOVERNANCE_YAML` in the shell is preserved. |
| `gateway start hermes` | `build_gateway_env()` uses the same `setdefault` pattern; logs `Hermes governance config: …` on startup. |

| Env | Points to | Read by |
|-----|-----------|---------|
| `HERMES_GOVERNANCE_YAML` | Runtime `governance/tools.yaml` | Plugin gate, adapter |
| `IF_DYNAMIC_BUNDLE_MANIFEST` | Runtime `governance/actions.manifest` | Dynamic bundle at backend boot (registers all catalog generic action IDs) |
| `IF_AGENT_ADAPTER_SOCKET` | Adapter UDS | Plugin → adapter validate calls |

To use a custom governed-tool set without editing runtime yaml, export
`HERMES_GOVERNANCE_YAML` **before** `start hermes` / `gateway start hermes`. Gateway E2E
and catalog live tests rely on this (temp throwaway yaml). See
[`tests/hermes_gateway/README.md`](../../tests/hermes_gateway/README.md).

## Architecture

```
LLM → governed tool(args + reason)
  → intentframe-gate plugin (Hermes process, httpx)
  → POST /validate-tool on ~/.intentframe/integrations/hermes/adapter.sock
  → hermes-adapter sidecar (own venv, if-integration-bridge-client)
  → POST /validate on ~/.intentframe/backend/bridge.sock
  → IntentFrame runtime + validate_only executor
  → ALLOW → Hermes original handler executes locally
  → BLOCK → JSON error, no side effect
```

The plugin hooks `registry.register` so MCP refresh cannot silently reinstall unwrapped handlers.

## Manual install

```bash
ln -sf "$(pwd)/integrations/hermes/plugin/intentframe-gate" \
  ~/.hermes/plugins/intentframe-gate
```

Enable in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - intentframe-gate
```

Export env from `agent.json` (or set in the shell before `start` / `gateway start`):

- `IF_AGENT_ADAPTER_SOCKET=~/.intentframe/integrations/hermes/adapter.sock`
- `HERMES_GOVERNANCE_YAML=~/.intentframe/integrations/hermes/governance/tools.yaml` (optional override path for governed-tool set)

## Adding a governed tool

1. Add an entry to `governance/tools.yaml`.
2. Add a mapper in `adapter/src/hermes_adapter/mapper.py` (or reuse a mapper kind).
3. Add the IntentFrame action to `agent.json` `action_types` if new.
4. Add policy constraints in `policy.yaml`.
5. Add mapper unit test + optional E2E probe.

No plugin code changes are required when the mapper kind already exists.

If the tool can emit **multiple IntentFrames per call** (like V4A `patch`), follow
the `map_patch` pattern in `mapper.py`: scoped per-op `content` for writes (not
the full multi-file blob), per-op reason suffix, and batch context in `data`
(`patch_op_index`, `patch_op_count`, `patch_operations`) so AE/Guardian can judge
each intent honestly. See [`docs/delete-host-file-validation.md`](../../docs/delete-host-file-validation.md)
(multi-intent + Hermes patch mapper).

## Manual acceptance checklist

1. `bin/intentframe-integrations install hermes`
2. `bin/intentframe-integrations start hermes`
3. `bin/intentframe-integrations integrate hermes`
4. `bin/intentframe-integrations doctor hermes`
5. `bin/intentframe-integrations gateway start hermes --api-server`
6. Ask LLM to run `echo ok` with a reason → executes
7. Ask LLM to run `sudo echo intentframe-e2e-block-probe` → blocked by IntentFrame policy (`sudo` pattern)
8. Ask LLM to `write_file` under `~/…` with a reason → executes (deterministic ALLOW)
9. Ask LLM to `write_file` to `/etc/…` → blocked by host-path policy (deterministic)
10. Ask LLM to `patch` with V4A `*** Delete File: ~/…` → may ALLOW or BLOCK (semantic;
    passes path policy; Guardian decides). Not a guaranteed execute.
11. Ask LLM to `patch` with V4A `*** Delete File: /etc/…` → blocked by host-path policy (deterministic)

## Live integration tests (all governed tools)

Deterministic adapter + plugin gate probes (no LLM) against a running Hermes stack:

```bash
./tests/scripts/test-hermes-integration.sh
```

Covers all four Hermes governed tools (`terminal`, `process`, `write_file`, `patch`)
including V4A `patch` multi-intent write+delete. Requires `OPENAI_API_KEY` (backend startup).

## Gateway E2E test (opt-in)

See [`tests/hermes_gateway/README.md`](../../tests/hermes_gateway/README.md).

```bash
RUN_HERMES_GATEWAY_E2E=1 \
  uv run --with httpx --package intentframe-integrations-cli \
  python tests/hermes_gateway/test_gateway_e2e.py
```

Requires `OPENAI_API_KEY`. Covers ALLOW/BLOCK for all four Hermes governed tools (`terminal`, `process`,
`write_file`, `patch`), including V4A mixed write+delete multi-intent `patch` probes.

Full run (passes 1, 2a, 2b) is green as of 2026-06-23. The harness seeds `patch replace`
targets, uses pass-unique markers, and explicit block prompts — see
[Probe harness determinism](../../tests/hermes_gateway/README.md#probe-harness-determinism).
Integration snapshot: [`docs/hermes-intentframe-state-report.md`](../../docs/hermes-intentframe-state-report.md).

## Toolsets + provider payload test (opt-in)

Proves intentframe-gate schema changes (`reason` required) reach OpenAI’s `tools=`
parameter — not just `/v1/toolsets` or the local registry probe.

```bash
RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh
```

Requires `OPENAI_API_KEY`. One `chat.completions` round-trip (~11k input tokens, ~17
tools). See [`tests/hermes_gateway/README.md`](../../tests/hermes_gateway/README.md#toolsets--provider-payload-test-opt-in-networked-llm).
