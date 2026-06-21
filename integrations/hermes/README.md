# Hermes integration

Hermes does **not** ship an IntentFrame executor pack or runtime. This folder provides:

| Path | Purpose |
|------|---------|
| `agent.json` | Agent profile, adapter socket, exported `env` for Hermes plugin |
| `policy.yaml` | RUN_COMMAND rules seeded into policy-registry |
| `adapter/` | Hermes adapter sidecar (bridge client, tool mapping, HTTP/UDS server) |
| `plugin/intentframe-terminal/` | Thin Hermes plugin — schema override + adapter gate |

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

## Commands

```bash
bin/intentframe-integrations install hermes [--version VERSION] [--force]
bin/intentframe-integrations start hermes
bin/intentframe-integrations integrate hermes [--copy] [--skip-config]
bin/intentframe-integrations doctor hermes [--install-only]
bin/intentframe-integrations gateway start hermes [--api-server]
bin/intentframe-integrations gateway stop hermes
bin/intentframe-integrations run hermes
bin/intentframe-integrations stop
```

`install hermes` installs Hermes Agent into the orchestrator-managed venv.
`integrate hermes` symlinks the plugin to `$HERMES_HOME/plugins/intentframe-terminal`, merges
`plugins.enabled` in `$HERMES_HOME/config.yaml`, and syncs the adapter venv at
`~/.intentframe/integrations/hermes/.venv`.

## Architecture

```
LLM → terminal(command, reason)
  → intentframe-terminal plugin (Hermes process, httpx)
  → POST /validate-tool on ~/.intentframe/integrations/hermes/adapter.sock
  → hermes-adapter sidecar (own venv, if-integration-bridge-client)
  → POST /validate on ~/.intentframe/backend/bridge.sock
  → IntentFrame runtime + validate_only executor
  → ALLOW → Hermes terminal_tool executes locally
  → BLOCK → JSON error, no shell
```

The plugin never holds the bridge secret. Only the adapter sidecar talks to the generic
IntentFrame backend bridge.

## Manual install

```bash
ln -sf "$(pwd)/integrations/hermes/plugin/intentframe-terminal" \
  ~/.hermes/plugins/intentframe-terminal
```

Enable in `~/.hermes/config.yaml`:

```yaml
plugins:
  enabled:
    - intentframe-terminal
```

Export env from `agent.json`:

- `IF_AGENT_ADAPTER_SOCKET=~/.intentframe/integrations/hermes/adapter.sock`

Start the runtime and adapter:

```bash
bin/intentframe-integrations start hermes
```

Then restart your Hermes gateway.

## Manual acceptance checklist

1. `bin/intentframe-integrations install hermes`
2. `bin/intentframe-integrations start hermes`
3. `bin/intentframe-integrations integrate hermes`
4. `bin/intentframe-integrations doctor hermes`
5. `bin/intentframe-integrations gateway start hermes --api-server`
6. Ask LLM to run `echo ok` with a reason → executes
7. Ask LLM to run `sudo echo intentframe-e2e-block-probe` → blocked by IntentFrame policy (`sudo` pattern)

## What the CLI configures (and what it does not)

| Step | Configures |
|------|------------|
| `install hermes` | Managed Hermes venv under `~/.intentframe/integrations/hermes/` |
| `start hermes` | IntentFrame backend + adapter sidecar |
| `integrate hermes` | Plugin symlink, `plugins.enabled` merge (with `config.yaml.intentframe.bak`), adapter venv sync |
| `gateway start hermes` | Launches `hermes gateway run` (+ optional API server); does **not** set LLM model/provider |

Hermes LLM settings (`model.provider`, `model.name`, `model.api_mode`) remain the user's
responsibility in `$HERMES_HOME/config.yaml` / `.env`. Only the opt-in gateway E2E test
seeds OpenAI defaults in an isolated sandbox — see below.

`integrate hermes` merges `plugins.enabled` in place when possible instead of rewriting the
full config file.

## Gateway E2E test (opt-in)

Full production journey with isolated `HOME` / `HERMES_HOME` (does not touch real
`~/.hermes` or `~/.intentframe/integrations/hermes`).

**Detailed guide:** [`tests/hermes_gateway/README.md`](../../tests/hermes_gateway/README.md)
(log paths, troubleshooting, ALLOW/BLOCK semantics).

Quick run:

```bash
RUN_HERMES_GATEWAY_E2E=1 \
  uv run --with httpx --package intentframe-integrations-cli \
  python tests/hermes_gateway/test_gateway_e2e.py

RUN_HERMES_GATEWAY_E2E=1 ./tests/scripts/test-hermes-gateway-e2e.sh
```

Requires `OPENAI_API_KEY` (IntentFrame backend + Hermes gateway LLM). E2E seeds isolated
`$HERMES_HOME` with `openai-api`, `api_mode: chat_completions`, and `gpt-4o-mini` (override:
`INTENTFRAME_HERMES_E2E_MODEL`). Hermes 0.17 otherwise auto-picks OpenAI Responses API for
`api.openai.com`, which breaks `gpt-4o-mini`.

The test prints **sandbox log paths** at activation and before `/v1/responses` — tail those
files, not real `~/.intentframe`, while debugging.

Covers pass 1 (greenfield), pass 2a (reuse managed install), pass 2b (external Hermes via
`HERMES_BIN`), and `/v1/responses` ALLOW/BLOCK. Each sandbox lives under `/tmp/hg*` and is
removed after that run only.
