# hermes-adapter

Per-agent sidecar for Hermes ↔ IntentFrame validate-only integration.

The Hermes plugin calls this adapter over UDS; the adapter calls the generic
IntentFrame bridge (`~/.intentframe/backend/bridge.sock`) using
`if-integration-bridge-client`.

## Run (normally via CLI)

```bash
bin/intentframe-integrations start hermes
```

Manual:

```bash
export IF_AGENT_BRIDGE_SECRET=...
export IF_SECURITY_BRIDGE_SOCKET=~/.intentframe/backend/bridge.sock
export INTENTFRAME_USER_ID=dev_user
export INTENTFRAME_AGENT_ID=hermes

python -m hermes_adapter.main --socket ~/.intentframe/integrations/hermes/adapter.sock
```

## HTTP API (UDS)

- `GET /health` — liveness
- `POST /validate-tool` — `{ "tool": "terminal", "args": { "command": "...", "reason": "..." } }`
