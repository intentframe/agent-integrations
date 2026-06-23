# if-integration-backend

Generic **IntentFrame validate-only** platform: one runtime, one noop executor pack (`validate_only`), one UDS bridge.

Agent profiles live under `../integrations/` (e.g. `integrations/hermes/`) — each ships `agent.json` + `policy.yaml` only, no executor packs.

**Dynamic bundle** (`bundles/dynamic.py`): agent-agnostic pass-through bundle. Reads
`IF_DYNAMIC_BUNDLE_MANIFEST` (comma-separated action IDs). If unset, registers nothing.
Hermes sets this env in `agent.json` pointing at runtime `actions.manifest`.

## Quick start

From the **repo root** (uv workspace):

```bash
uv sync --all-packages
export OPENAI_API_KEY=sk-...
export INTENTFRAME_USER_ID=test_user

uv run --package if-integration-backend if-integration-backend start
uv run --package if-integration-backend if-integration-backend seed-policy --skip-if-exists
uv run --package if-integration-backend if-integration-backend test
```

`start` brings up **IntentFrame core + executor + validate bridge** (single command).  
`stop` tears down **everything** including the bridge.

`test` runs backend-owned integration checks:

- **Core connection** — direct `Actor` handshake + submit against IntentFrame core
- **Bridge connection** — `httpx` against `bridge.sock` (`412` without handshake, then handshake + validate)

## Full e2e test (automated)

From the repo root:

```bash
./scripts/e2e.sh
```

Requires `node`, `npm`, and `OPENAI_API_KEY`. Bootstraps `uv` if missing. See root `README.md`.

## Hermes agent

From the **repo root**:

```bash
bin/intentframe-integrations start hermes
bin/intentframe-integrations seed hermes --skip-if-exists
bin/intentframe-integrations policy reload hermes   # after editing runtime policy
```

Runtime policy: `~/.intentframe/integrations/hermes/policy.yaml` (see `policy show|reload|set|reset`).

Or via the internal runtime CLI:

```bash
uv run --package if-integration-backend if-integration-backend start \
  --agent-config ../integrations/hermes/agent.json
```

State: `~/.intentframe/backend/` · Bridge: `~/.intentframe/backend/bridge.sock`

## Layout

| Path | Purpose |
|------|---------|
| `src/if_security_backend/` | **Runtime only** — bridge, supervisor, executor pack, CLI |
| `src/.../config/` | Bundled YAML/JSON (profiles + default agent) |
| `tests/integration/` | Backend integration tests (core + bridge HTTP) |
| `../if-integration-clients/` | Reusable bridge clients (Python + TypeScript) |
| `../tests/agents/` | E2e agent configs |
| `../tests/examples/` | Client library example scripts |

Bridge clients use Jarvis-style lifecycle: `POST /handshake` once at init, then `POST /validate`.
