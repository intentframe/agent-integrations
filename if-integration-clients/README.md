# if-integration-clients

Reusable clients for the IntentFrame **validate bridge** (HTTP over Unix socket).

| Language | Package | Import |
|----------|---------|--------|
| Python | `if-integration-bridge-client` | `from if_integration_bridge import BridgeClient` |
| TypeScript | `@if-integration/bridge-client` | `import { BridgeClient } from "@if-integration/bridge-client"` |

Both expose the same Jarvis-style flow: **`handshake()` once at agent init**, then **`validate()` / `validateRunCommand()`** per action.

Environment variables (or explicit config):

- `IF_SECURITY_BRIDGE_SOCKET` — UDS path (default `~/.intentframe/backend/bridge.sock`)
- `IF_AGENT_BRIDGE_SECRET` — bridge Bearer token

## Install (monorepo workspace)

From the **repo root**:

```bash
# Python
uv sync --all-packages
uv run --package if-integration-bridge-client python -c "from if_integration_bridge import BridgeClient"

# TypeScript
npm install
npm run build
```

Examples live in `../tests/examples/`. Depend via monorepo workspace (npm `"*"` for sibling packages; uv workspace for Python).

See `python/README.md` and `typescript/README.md`.
