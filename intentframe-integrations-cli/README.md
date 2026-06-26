# IntentFrame Integrations CLI

User-facing orchestrator for agent profiles under `integrations/`. Delegates runtime work to
`if-integration-backend` and manages per-agent adapter sidecars.

**Hermes users:** start with the [root README](../README.md) (install + three commands to chat).
Full command reference: [docs/hermes-cli.md](../docs/hermes-cli.md).

## Hermes (summary)

```bash
export OPENAI_API_KEY=sk-...
intentframe-integrations up hermes
hermes dashboard
```

```bash
intentframe-integrations install hermes
intentframe-integrations integrate hermes
intentframe-integrations uninstall hermes
intentframe-integrations doctor hermes
intentframe-integrations governance list hermes
intentframe-integrations policy show hermes
intentframe-integrations stop
```

See [docs/hermes-cli.md](../docs/hermes-cli.md) for every flag, env var, and advanced gateway flow.

## Run from repo

```bash
bin/intentframe-integrations up hermes
```

Or:

```bash
uv run --package intentframe-integrations-cli intentframe-integrations up hermes
```

## Other agents

Agent profiles live under `integrations/<agent>/agent.json`. Use `start --agent-config` for custom profiles.
