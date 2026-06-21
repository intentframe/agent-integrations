# IntentFrame Integrations CLI

User-facing orchestrator for agent profiles under `integrations/`. Delegates runtime work to
`if-integration-backend` and manages per-agent adapter sidecars.

## Commands

```bash
intentframe-integrations install hermes [--version VERSION] [--force]
intentframe-integrations start hermes [--no-seed] [--skip-if-exists]
intentframe-integrations start --agent-config path/to/agent.json [--no-seed]
intentframe-integrations integrate hermes [--copy] [--skip-config]
intentframe-integrations gateway start hermes [--api-server] [--api-port PORT] [--api-key KEY]
intentframe-integrations gateway stop hermes
intentframe-integrations run hermes [-- extra hermes gateway args]
intentframe-integrations stop
intentframe-integrations status
intentframe-integrations seed hermes [--skip-if-exists]
intentframe-integrations test [--agent-config path/to/agent.json]
intentframe-integrations doctor hermes [--install-only]
```

Run from repo root via `bin/intentframe-integrations` or:

```bash
uv run --package intentframe-integrations-cli intentframe-integrations start hermes
```

## Hermes production flow

Greenfield user (no Hermes installed):

```bash
export OPENAI_API_KEY=sk-...
bin/intentframe-integrations install hermes
bin/intentframe-integrations start hermes
bin/intentframe-integrations integrate hermes
bin/intentframe-integrations doctor hermes
bin/intentframe-integrations gateway start hermes --api-server
```

Returning user / one-liner:

```bash
export OPENAI_API_KEY=sk-...
bin/intentframe-integrations run hermes
```

`install hermes` installs Hermes Agent into a managed venv at
`~/.intentframe/integrations/hermes/hermes-agent-venv/`. Hermes data lives under
`HERMES_HOME` (default `~/.hermes`).

Hermes binary resolution order:

1. `HERMES_BIN` if set
2. Managed install from `install hermes`
3. `hermes` on `PATH` (standalone user install)

## Hermes stack

1. `install hermes` — Hermes Agent CLI (managed venv, pinned version)
2. `start hermes` — backend bridge + adapter sidecar (`~/.intentframe/integrations/hermes/`)
3. `integrate hermes` — plugin symlink + adapter venv sync + config merge
4. `gateway start hermes` — launch Hermes gateway (optionally with API server)
5. `stop` — stop gateway started by orchestrator, adapters, and backend runtime

`gateway start hermes` always invokes `hermes gateway run` (foreground process). Extra gateway
args are normalized to run flags only; service subcommands are ignored. Stop uses process-group
termination and verifies the PID is still a Hermes gateway before trusting stale PID files.

The CLI does **not** configure Hermes LLM model or provider — only plugin install, config merge,
adapter sync, and gateway lifecycle.

See `integrations/hermes/README.md` for architecture. Opt-in gateway E2E (sandbox, log paths,
troubleshooting): `tests/hermes_gateway/README.md`.
