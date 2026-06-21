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
7. Ask LLM to run `sudo rm -rf /` → blocked by IntentFrame
