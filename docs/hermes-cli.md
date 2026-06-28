# Hermes CLI reference

`intentframe-integrations` orchestrates IntentFrame + Hermes. Install it via
[install-hermes-plugin.sh](../scripts/install-hermes-plugin.sh) (full Hermes install by default; `--headless` for Docker/CI) or from this repo's `bin/`.

**CLI on PATH:** the installer symlinks `intentframe-integrations` from `~/.intentframe/agent-integrations/.venv/bin/` into `~/.local/bin` and `/usr/local/bin` when that directory is writable (root, Docker, many Linux installs). On Mac, open a new terminal and run `command -v intentframe-integrations` to confirm.

User-facing quick start: [README.md](../README.md).

Known limitations (community install / uninstall caveats): [hermes-known-limitations.md](hermes-known-limitations.md).

## Install

The [install script](../scripts/install-hermes-plugin.sh) downloads the integration pack, installs Hermes (if missing), copies the plugin, and symlinks the CLI. It is the **only** way to do a fresh install after `uninstall`.

### Default (end users)

Full Hermes install — setup wizard runs when needed:

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
```

### Headless (testers / CI / Docker)

Skips Hermes setup wizard and browser engine. You must set `OPENAI_API_KEY` yourself (run `hermes setup` if chat returns 401):

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash -s -- --headless
```

From a git clone:

```bash
bash scripts/install-hermes-plugin.sh              # full
bash scripts/install-hermes-plugin.sh --headless   # headless
```

### Pin a git ref (branch, tag, or commit)

Use the **same ref** in the script URL and `--ref` (or `REF=`). `VERSION=` is a deprecated alias for `REF=`.

| Tier | Command |
|------|---------|
| Latest | `curl -fsSL …/raw/main/scripts/install-hermes-plugin.sh \| bash` |
| Branch (pre-merge) | `curl -fsSL …/raw/my-branch/… \| bash -s -- --ref my-branch --headless` |
| Release tag | `curl -fsSL …/raw/v0.2.0/… \| bash -s -- --ref v0.2.0` |
| Commit SHA | `curl -fsSL …/raw/<sha>/… \| bash -s -- --ref <sha>` |

After install, `intentframe-integrations doctor hermes` shows the pinned ref from `~/.intentframe/agent-integrations/.install-manifest.json`.

**Note:** `intentframe-integrations install hermes --version` pins the **Hermes Agent** pip package — not the integration pack ref.

### PATH and shell rc

Every install:

1. Symlinks `intentframe-integrations` → `~/.local/bin/`
2. Symlinks `intentframe-integrations` → `/usr/local/bin/` when writable (root / Docker / many Linux installs)

Additionally, the installer **may** append to `~/.zshrc`, `~/.bashrc`, or `~/.profile`:

- Only if the file **exists**
- Only if it does **not** already contain `.local/bin` (uv, Hermes, or a prior install often satisfy this)

When appended, the block is tagged:

```bash
# Added by IntentFrame Hermes installer
export PATH="$HOME/.local/bin:$PATH"
```

If Hermes already put `~/.local/bin` on PATH, you will **not** see that comment — PATH still works via the existing line.

**Check in a new terminal:**

```bash
command -v intentframe-integrations
command -v hermes
```

### `integrate` vs install script

| Command | Downloads pack? | When to use |
|---------|-----------------|-------------|
| `curl … install-hermes-plugin.sh` | Yes | First install; **only** way to reinstall after `uninstall` |
| `intentframe-integrations integrate hermes` | No | Re-wire plugin/config while pack still exists at `~/.intentframe/agent-integrations` |

`integrate` reads the plugin from the on-disk pack. After `uninstall`, the pack and CLI are gone — run the install script again.

## Happy path

After [install](hermes-cli.md#install), the installer starts the **IntentFrame Control Plane** at `http://127.0.0.1:9720`.

```bash
# Control plane (operator UI — started by installer)
open http://127.0.0.1:9720

# From Control Plane or CLI: start enforcement stack
export OPENAI_API_KEY=sk-...
intentframe-integrations up hermes      # backend + adapter + gateway

# Hermes chat (separate from control plane)
hermes dashboard                        # http://127.0.0.1:9119/chat
intentframe-integrations stop           # enforcement stack only (not control plane)
```

See [intentframe-control-plane.md](intentframe-control-plane.md) for port registry and lifecycle.

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

Stop the stack first, then uninstall:

```bash
intentframe-integrations stop || true
intentframe-integrations uninstall hermes              # IntentFrame only; Hermes stays
intentframe-integrations uninstall hermes --remove-hermes   # IntentFrame + all of Hermes
```

If the CLI is already gone, use the repo copy:

```bash
cd /path/to/agent-integrations
./bin/intentframe-integrations uninstall hermes --remove-hermes
```

#### What gets removed

| Target | `uninstall hermes` | `+ --remove-hermes` |
|--------|-------------------|---------------------|
| `~/.hermes/plugins/intentframe-gate` | yes | yes |
| `intentframe-gate` in `~/.hermes/config.yaml` | yes | yes |
| IntentFrame keys in `~/.hermes/.env` (`IF_*`, `HERMES_GOVERNANCE_YAML`, etc.) | yes | yes |
| `~/.hermes/*.intentframe.bak` config backups | yes | yes |
| Entire `~/.intentframe/` (pack, venv, backend, logs, policy, adapter) | yes | yes |
| `intentframe-integrations` CLI symlinks (`~/.local/bin`, `/usr/local/bin`) | yes | yes |
| Installer PATH block (`# Added by IntentFrame Hermes installer` only) | yes | yes |
| Entire `~/.hermes/` (config, agent checkout, sessions, logs, skills, cron) | **no** | **yes** |
| `hermes` CLI symlinks (`~/.local/bin`, `/usr/local/bin`) | **no** | **yes** |

With `--remove-hermes`, all Hermes **user data** under `~/.hermes` is deleted, plus `hermes` CLI symlinks. On a normal per-user install that is a full Hermes wipe. On **root/Linux FHS** installs, Hermes code under `/usr/local/lib/hermes-agent/` is left behind — see [known limitations](hermes-known-limitations.md#--remove-hermes-does-not-remove-root-fhs-hermes-code).

#### What is **not** removed

| Left behind | Why |
|-------------|-----|
| `/usr/local/lib/hermes-agent/` (root FHS Hermes install on Linux) | Not in uninstall scope yet — [manual cleanup](hermes-known-limitations.md#--remove-hermes-does-not-remove-root-fhs-hermes-code) |
| `export PATH=…~/.local/bin…` from **uv** or **official Hermes** (no IntentFrame marker) | Uninstall only strips our tagged block |
| Homebrew packages (e.g. `ffmpeg` installed during Hermes setup) | System packages |
| Git dev clone (`~/…/agent-integrations`) | Not part of user install |
| Docker named volumes | Use `docker compose … down -v` separately |

#### Verify

Run in a **new terminal** after uninstall:

```bash
command -v intentframe-integrations || echo "IF CLI: gone"
command -v hermes || echo "hermes CLI: gone"
test -e ~/.intentframe || echo "~/.intentframe: gone"
test -e ~/.hermes || echo "~/.hermes: gone"
grep -F 'IntentFrame Hermes installer' ~/.zshrc ~/.bashrc ~/.profile 2>/dev/null \
  || echo "IntentFrame installer rc block: gone (or never added)"
```

After `uninstall hermes` (without `--remove-hermes`): `~/.hermes` should still exist; `~/.intentframe` and `intentframe-integrations` should be gone.

After `uninstall hermes --remove-hermes`: all four checks should report **gone**.

#### Manual fallback (CLI already deleted)

IntentFrame only:

```bash
rm -rf ~/.intentframe
rm -f ~/.local/bin/intentframe-integrations /usr/local/bin/intentframe-integrations
rm -rf ~/.hermes/plugins/intentframe-gate
```

IntentFrame + Hermes:

```bash
rm -rf ~/.intentframe ~/.hermes
rm -f ~/.local/bin/intentframe-integrations ~/.local/bin/hermes
rm -f /usr/local/bin/intentframe-integrations /usr/local/bin/hermes
# root/Linux FHS Hermes only:
sudo rm -rf /usr/local/lib/hermes-agent
```

### Reinstall

`uninstall` deletes the CLI and `~/.intentframe/agent-integrations`. There is nothing left to `integrate`. Always re-run the install script:

```bash
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
# or headless:
curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash -s -- --headless
```

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

### Control plane (operator UI)

Separate from Hermes dashboard. Default: `http://127.0.0.1:9720`.

```bash
intentframe-integrations control-plane start
intentframe-integrations control-plane stop
intentframe-integrations control-plane status
intentframe-integrations control-plane serve   # foreground
```

`stop` stops the enforcement stack only — not the control plane. See [intentframe-control-plane.md](intentframe-control-plane.md).

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

Written to `~/.intentframe/.env` on install (control plane):

| Variable | Purpose |
|----------|---------|
| `INTENTFRAME_CONTROL_PLANE_HOST` | Bind host (default `127.0.0.1`) |
| `INTENTFRAME_CONTROL_PLANE_PORT` | UI port (default `9720`) |
| `INTENTFRAME_CONTROL_PLANE_TOKEN` | Optional bearer token for `/api/*` |

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
