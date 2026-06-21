# IntentFrame Integrations CLI

User-facing orchestrator for agent profiles under `integrations/`. Delegates runtime work to `if-integration-backend` (not upstream `intentframe` or `intentframe-gateway-cli`).

## Commands

```bash
intentframe-integrations start hermes [--no-seed] [--skip-if-exists]
intentframe-integrations start --agent-config path/to/agent.json [--no-seed]
intentframe-integrations stop
intentframe-integrations status
intentframe-integrations seed hermes [--skip-if-exists]
intentframe-integrations seed --agent-config path/to/agent.json [--skip-if-exists]
intentframe-integrations test [--agent-config path/to/agent.json]
intentframe-integrations doctor hermes
```

Run from repo root via `bin/intentframe-integrations` or:

```bash
uv run --package intentframe-integrations-cli intentframe-integrations start hermes
```
