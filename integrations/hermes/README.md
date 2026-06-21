# Hermes integration (client only)

Hermes does **not** ship an IntentFrame executor pack or runtime. This folder provides:

| File | Purpose |
|------|---------|
| `agent.json` | Bridge secret, `agent_id`, `user_id`, exported `env` for plugin/CLI |
| `policy.yaml` | RUN_COMMAND rules seeded into policy-registry |

## Start / stop (IntentFrame Integrations CLI)

From the **repo root**:

```bash
uv sync --all-packages
export OPENAI_API_KEY=sk-...

bin/intentframe-integrations start hermes
bin/intentframe-integrations status
bin/intentframe-integrations stop
```

Or after sync:

```bash
uv run --package intentframe-integrations-cli intentframe-integrations start hermes
```

`start hermes` starts the validate runtime + bridge with this agent config and seeds policy.

Hermes plugin (Phase 3): read `agent.json` → `POST /validate` on `IF_SECURITY_BRIDGE_SOCKET` → run terminal locally if `allowed`.

## Env for an existing Hermes install

Export from `agent.json` `env` block (or use `integrations/hermes/agent.json` values):

- `INTENTFRAME_USER_ID=dev_user`
- `INTENTFRAME_AGENT_ID=hermes`
- `IF_AGENT_BRIDGE_SECRET=…`
- `IF_SECURITY_BRIDGE_SOCKET=~/.intentframe/backend/bridge.sock`

Then restart your Hermes gateway after the IntentFrame plugin is enabled.
