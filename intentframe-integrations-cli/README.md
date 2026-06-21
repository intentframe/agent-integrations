# IntentFrame Integrations CLI

User-facing orchestrator for agent profiles under `integrations/`. Delegates runtime work to
`if-integration-backend` and manages per-agent adapter sidecars.

## Commands

```bash
intentframe-integrations start hermes [--no-seed] [--skip-if-exists]
intentframe-integrations start --agent-config path/to/agent.json [--no-seed]
intentframe-integrations integrate hermes [--copy] [--skip-config]
intentframe-integrations run hermes [-- extra hermes gateway args]
intentframe-integrations stop
intentframe-integrations status
intentframe-integrations seed hermes [--skip-if-exists]
intentframe-integrations test [--agent-config path/to/agent.json]
intentframe-integrations doctor hermes
```

Run from repo root via `bin/intentframe-integrations` or:

```bash
uv run --package intentframe-integrations-cli intentframe-integrations start hermes
```

## Hermes one-liner

```bash
export OPENAI_API_KEY=sk-...
bin/intentframe-integrations run hermes
```

Starts IntentFrame runtime + bridge + Hermes adapter, installs the plugin, syncs the adapter
venv, applies env, and launches `hermes gateway`.

## Hermes flow

1. `start hermes` — backend bridge + adapter sidecar (`~/.intentframe/integrations/hermes/`)
2. `integrate hermes` — plugin symlink + adapter venv sync
3. Export `IF_AGENT_ADAPTER_SOCKET` (printed by `integrate`)
4. Restart Hermes gateway

See `integrations/hermes/README.md` for architecture details.
