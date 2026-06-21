# agent-integrations

IntentFrame agent integration monorepo: validate-only backend, bridge clients, and e2e tests.

## Quick start (e2e)

From a fresh clone, one command installs everything and runs the full test pipeline:

```bash
./scripts/e2e.sh
```

Requires `node`, `npm`, and `OPENAI_API_KEY` in the environment.

Reset local artifacts first:

```bash
./scripts/clean-project.sh
./scripts/e2e.sh
```

## Layout

| Path | Purpose |
|------|---------|
| `if-integration-backend/` | Runtime: supervisor, bridge, executor pack, backend integration tests |
| `if-integration-clients/` | Reusable bridge clients (Python + TypeScript) |
| `tests/agents/` | E2e agent configs (`agent.json` + `policy.yaml`) |
| `tests/examples/` | Thin client library examples |
| `tests/scripts/` | `e2e.sh`, `clean-project.sh` |
| `pyproject.toml` | uv workspace root |
| `package.json` | npm workspaces root |

## Workspace commands

```bash
# Python (all workspace packages)
uv sync --all-packages
uv run --package if-integration-backend if-integration-backend start

# TypeScript (all workspaces)
npm install
npm run build
```

See `if-integration-backend/README.md` and `if-integration-clients/README.md` for package-specific docs.
