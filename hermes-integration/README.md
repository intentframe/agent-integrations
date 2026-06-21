# Hermes agent integration (client only)

Hermes does **not** ship an IntentFrame executor pack or runtime. It only provides:

| File | Purpose |
|------|---------|
| `agent.json` | Bridge secret, `agent_id`, `user_id`, exported `env` for plugin/CLI |
| `policy.yaml` | RUN_COMMAND rules seeded into policy-registry |

## Start / stop (via shared backend)

All commands run from [`../if-integration-backend/`](../if-integration-backend/):

```bash
cd ../if-integration-backend
export OPENAI_API_KEY=sk-...
uv sync

uv run if-integration-backend start --agent-config ../hermes-integration/agent.json
uv run if-integration-backend seed-policy --agent-config ../hermes-integration/agent.json --skip-if-exists

# Stop core + bridge together
uv run if-integration-backend stop
```

Hermes plugin (Phase 3): read `agent.json` → `POST /validate` on `IF_SECURITY_BRIDGE_SOCKET` → run terminal locally if `allowed`.
