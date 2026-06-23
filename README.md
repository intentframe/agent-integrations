# agent-integrations

IntentFrame agent integration monorepo: validate-only backend, bridge clients, and e2e tests.

## Quick start (Hermes)

From repo root after `uv sync --all-packages`:

```bash
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

See `integrations/hermes/README.md` for details. Governed-tool terminology:
[`docs/agent-tool-gating.md`](docs/agent-tool-gating.md#terminology-what-governed-means).
Hermes + IntentFrame integration: [`docs/hermes-intentframe-integration-guide.md`](docs/hermes-intentframe-integration-guide.md).
Gateway plugin preload: [`docs/hermes-plugin-registration-order.md`](docs/hermes-plugin-registration-order.md).

## Quick start (e2e)

From a fresh clone, one command installs everything and runs the full test pipeline:

```bash
./scripts/e2e.sh
```

Requires `node`, `npm`, and `OPENAI_API_KEY` in the environment.

Optional Hermes gateway E2E (slow, networked, LLM-dependent; isolated sandbox):

```bash
RUN_HERMES_GATEWAY_E2E=1 ./scripts/e2e.sh
```

See [`tests/hermes_gateway/README.md`](tests/hermes_gateway/README.md) for log paths and troubleshooting.

Reset local artifacts first (clears `~/.intentframe/backend`, `run`, and `integrations/` runtime config):

```bash
./scripts/clean-project.sh
./scripts/e2e.sh
```

## Layout

| Path | Purpose |
|------|---------|
| `bin/intentframe-integrations` | User-facing CLI (start/stop/status per agent profile) |
| `intentframe-integrations-cli/` | Orchestrator package (delegates to `if-integration-backend`) |
| `integrations/` | Agent profiles (`agent.json` + `policy.yaml`) |
| `if-integration-backend/` | Runtime: supervisor, bridge, executor pack |
| `if-integration-clients/` | Reusable bridge clients (Python + TypeScript) |
| `tests/agents/` | E2e agent configs |
| `tests/examples/` | Client library examples |
| `tests/hermes_gateway/` | Opt-in Hermes gateway E2E (isolated sandbox) |
| `tests/scripts/` | `e2e.sh`, `test-hermes-gateway-e2e.sh`, `clean-project.sh` |
| `pyproject.toml` | uv workspace root |
| `package.json` | npm workspaces root |

## Workspace commands

```bash
uv sync --all-packages
bin/intentframe-integrations start hermes

# Lower-level runtime CLI (internal)
uv run --package if-integration-backend if-integration-backend test

# TypeScript workspaces
npm install
npm run build
```

See `if-integration-backend/README.md` and `if-integration-clients/README.md` for package-specific docs.
