# Hermes CLI reference

`intentframe-integrations` orchestrates IntentFrame + Hermes. Install it via
[install-hermes-plugin.sh](../scripts/install-hermes-plugin.sh) (symlinks to `/usr/local/bin` when writable and `~/.local/bin`) or from this repo's `bin/`.

**CLI on PATH:** the installer symlinks the real binary from `~/.intentframe/agent-integrations/.venv/bin/intentframe-integrations` into `/usr/local/bin` when that directory is writable (root, Docker, many Linux installs) and always into `~/.local/bin`. On Mac without a writable `/usr/local/bin`, open a new terminal after install (shell rc is updated). No sourcing required for direct `docker exec … intentframe-integrations` when `/usr/local/bin` is used.

User-facing quick start: [README.md](../README.md).

## Happy path

```bash
export OPENAI_API_KEY=sk-...
intentframe-integrations up hermes      # backend + adapter + gateway
hermes dashboard                        # http://localhost:9119/chat
intentframe-integrations stop           # tear down
```

## Command overview

### Install and integrate

```bash
intentframe-integrations install hermes [--version VERSION] [--force]
intentframe-integrations integrate hermes [--copy] [--skip-config]
intentframe-integrations doctor hermes [--install-only]
```

- **`install`** — Hermes Agent into `~/.intentframe/integrations/hermes/hermes-agent-venv/`
- **`integrate`** — copy plugin to `~/.hermes/plugins/intentframe-gate`, seed governance/policy templates, merge `plugins.enabled`
- **`doctor`** — verify binary, plugin, adapter socket

Hermes binary resolution order: `HERMES_BIN` → `hermes` on `PATH` → managed venv from `install`.

### Runtime

```bash
intentframe-integrations up hermes [--no-seed] [--skip-if-exists]
intentframe-integrations start hermes [--no-seed] [--skip-if-exists]
intentframe-integrations stop
intentframe-integrations status
```

| Command | Starts |
|---------|--------|
| **`up hermes`** | Backend + adapter + **gateway** — use this before `hermes dashboard` |
| **`start hermes`** | Backend + adapter only (tests, debugging) |

`up` requires `OPENAI_API_KEY` in the environment.

### Gateway (advanced)

```bash
intentframe-integrations gateway start hermes [--api-server] [--api-port PORT] [--api-key KEY]
intentframe-integrations gateway stop hermes
intentframe-integrations run hermes [-- extra hermes gateway args]
```

Use `gateway start --api-server` for HTTP `/v1/responses` testing. Normal chat via the dashboard does not need a separate `gateway start` if you already ran `up hermes`.

### Governance (which tools are gated)

**Governed** means IntentFrame validates before Hermes runs the native handler. It is not the same as “Hermes enabled the tool on `/v1/toolsets`.”

```bash
intentframe-integrations governance list hermes
intentframe-integrations governance enable hermes <tool>
intentframe-integrations governance disable hermes <tool>
```

**Restart Hermes gateway + adapter** after enable/disable. The IntentFrame backend does not need restart.

Runtime config: `~/.intentframe/integrations/hermes/governance/tools.yaml`

Terminology: [agent-tool-gating.md](agent-tool-gating.md#terminology-what-governed-means).

### Policy (ALLOW/BLOCK rules)

```bash
intentframe-integrations policy show hermes
intentframe-integrations policy reload hermes
intentframe-integrations policy set hermes /path/to/policy.yaml
intentframe-integrations policy reset hermes
```

Runtime file: `~/.intentframe/integrations/hermes/policy.yaml`

Policy changes apply immediately — no gateway restart.

### Other

```bash
intentframe-integrations seed hermes [--skip-if-exists]
intentframe-integrations test [--agent-config path/to/agent.json]
intentframe-integrations start --agent-config path/to/agent.json
```

## Environment variables

Written to `~/.hermes/.env` on install (plugin paths):

| Variable | Purpose |
|----------|---------|
| `IF_AGENT_ADAPTER_SOCKET` | Plugin → adapter UDS |
| `HERMES_GOVERNANCE_YAML` | Governed tool catalog |
| `IF_DYNAMIC_BUNDLE_MANIFEST` | Generic action IDs for policy |

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Required for `up hermes` and LLM chat |
| `HERMES_BIN` | Override Hermes binary |
| `HERMES_HOME` | Hermes config dir (default `~/.hermes`) |

Shell exports win over `agent.json` defaults (`setdefault` in `load_and_activate_pack`).

`gateway start hermes` logs the effective governance path on stderr:

```text
  Hermes governance config: /path/to/tools.yaml
```

## Hermes stack (what each layer does)

1. **`install hermes`** — Hermes Agent CLI (managed venv)
2. **`integrate hermes`** — plugin + runtime governance/policy templates
3. **`up hermes`** — backend bridge + adapter + Hermes gateway (ready for `hermes dashboard`)
4. **`start hermes`** — backend bridge + adapter only (low-level; tests/debug)
5. **`gateway start hermes`** — launch Hermes gateway only (optionally with API server)
6. **`stop`** — stop gateway started by orchestrator, adapters, and backend runtime

The CLI does **not** configure Hermes LLM model or provider — only plugin install, config merge, adapter sync, and gateway lifecycle. Use `hermes setup` or edit `~/.hermes/config.yaml` for LLM settings.

## Pack activation

Every command that loads an agent profile through `load_and_activate_pack()`:

1. Load `agent.json` → `IntegrationPack`
2. Apply `agent.json` `env` via `os.environ.setdefault` (explicit shell exports win)
3. For Hermes: seed runtime `governance/tools.yaml` and `generic_actions.manifest` if missing

Used by `up`, `start`, `integrate`, `doctor`, `gateway start`, `run`, and all `policy *` commands.

## Repo development

```bash
uv sync --all-packages
bin/intentframe-integrations up hermes
```

Or:

```bash
uv run --package intentframe-integrations-cli intentframe-integrations up hermes
```

Greenfield from repo root:

```bash
export OPENAI_API_KEY=sk-...
bin/intentframe-integrations install hermes
bin/intentframe-integrations integrate hermes
bin/intentframe-integrations up hermes
bin/intentframe-integrations doctor hermes
```

See [integrations/hermes/README.md](../integrations/hermes/README.md) for architecture and adding governed tools.

Opt-in gateway E2E: [tests/hermes_gateway/README.md](../tests/hermes_gateway/README.md).
