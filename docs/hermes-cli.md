# Hermes CLI reference

`intentframe-integrations` orchestrates IntentFrame + Hermes. Install it via
[install-hermes-plugin.sh](../scripts/install-hermes-plugin.sh) (full Hermes install by default; `--headless` for Docker/CI) or from this repo's `bin/`.

**CLI on PATH:** the installer symlinks the real binary from `~/.intentframe/agent-integrations/.venv/bin/intentframe-integrations` into `/usr/local/bin` when that directory is writable (root, Docker, many Linux installs) and always into `~/.local/bin`. On Mac without a writable `/usr/local/bin`, open a new terminal after install (shell rc is updated). No sourcing required for direct `docker exec … intentframe-integrations` when `/usr/local/bin` is used.

User-facing quick start: [README.md](../README.md).

## Install

**Default** (full Hermes install — setup wizard when needed):

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
```

**Headless** (skip Hermes setup wizard + browser engine — testers with `OPENAI_API_KEY` already set; same as Docker/CI):

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash -s -- --headless
```

From a git clone:

```bash
bash scripts/install-hermes-plugin.sh              # full
bash scripts/install-hermes-plugin.sh --headless   # headless
```

Pin a branch: `VERSION=my-branch curl -fsSL … | bash -s -- --headless`

After headless install, export `OPENAI_API_KEY` and run `hermes setup` if chat returns 401.

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
intentframe-integrations uninstall hermes [--remove-hermes]
intentframe-integrations doctor hermes [--install-only]
```

- **`install`** — Hermes Agent into `~/.intentframe/integrations/hermes/hermes-agent-venv/`
- **`integrate`** — re-wire an **already-installed** pack into Hermes: copy plugin to `~/.hermes/plugins/intentframe-gate`, seed governance/policy templates, merge `plugins.enabled`. Reads the plugin source from `~/.intentframe/agent-integrations` — it does **not** download anything. Use it after editing config or with `--reset-policy` / `--reset-governance`, not to reinstall.
- **`uninstall`** — remove all IntentFrame traces: plugin, entire `~/.intentframe`, CLI symlinks, installer PATH block in shell rc. Add `--remove-hermes` to also delete `~/.hermes` and `hermes` CLI symlinks.
- **`doctor`** — verify binary, plugin, adapter socket

> **After `uninstall` you must do a fresh install to use IntentFrame again.** Uninstall deletes the `~/.intentframe` pack and the `intentframe-integrations` CLI itself, so `integrate` is no longer available. Re-run the install script (see [Reinstall](#reinstall)).

### Uninstall

Remove IntentFrame only (Hermes stays):

```bash
intentframe-integrations stop
intentframe-integrations uninstall hermes
```

Remove IntentFrame **and** Hermes (all data):

```bash
intentframe-integrations uninstall hermes --remove-hermes
```

What gets removed:

| Target | `uninstall hermes` | `+ --remove-hermes` |
|--------|-------------------|---------------------|
| `~/.hermes/plugins/intentframe-gate` | yes | yes |
| `intentframe-gate` in `~/.hermes/config.yaml` | yes | yes |
| IntentFrame keys in `~/.hermes/.env` | yes | yes |
| Entire `~/.intentframe/` | yes | yes |
| `intentframe-integrations` CLI symlinks | yes | yes |
| Installer PATH block in `~/.zshrc` / `.bashrc` / `.profile` | yes | yes |
| Entire `~/.hermes/` (config, sessions, logs, skills, agent) | no | yes |
| `hermes` CLI symlinks | no | yes |

If the CLI is already gone, manual Hermes removal:

```bash
rm -rf ~/.hermes
rm -f ~/.local/bin/hermes /usr/local/bin/hermes
```

### Reinstall

`uninstall` removes the CLI and the `~/.intentframe` pack, so there is nothing left to `integrate`. To use IntentFrame again, always do a **fresh install**:

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
```

This re-downloads the pack, reinstalls the plugin, and puts the CLI back on PATH. There is no "reintegrate" shortcut after uninstall.

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
