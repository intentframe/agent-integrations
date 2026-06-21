# Agent integration template

Copy this folder to `integrations/<agent>/` and customize:

| Path | Purpose |
|------|---------|
| `agent.json` | Agent profile, adapter sidecar config, plugin env exports |
| `policy.yaml` | RUN_COMMAND rules seeded into policy-registry |
| `adapter/` | Agent adapter sidecar (bridge client, tool mapping, HTTP/UDS server) |
| `plugin/` | Thin agent plugin (Hermes uses `plugin/intentframe-terminal/`) |

Register the profile in `intentframe-integrations-cli/src/intentframe_integrations/paths.py`:

```python
AGENT_PROFILES = {
    "hermes": "integrations/hermes/agent.json",
    "<agent>": "integrations/<agent>/agent.json",
}
```

Commands:

```bash
bin/intentframe-integrations start <agent>
bin/intentframe-integrations integrate <agent>   # Hermes today; extend per agent
bin/intentframe-integrations doctor <agent>
```

See `integrations/hermes/` for the reference implementation.

Architecture:

```
Agent plugin → adapter sidecar (own venv) → IntentFrame bridge → runtime
```

The plugin should **not** receive bridge secrets. Only the adapter talks to
`~/.intentframe/backend/bridge.sock`.
