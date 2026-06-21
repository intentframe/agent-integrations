# intentframe-terminal (Hermes plugin)

External Hermes plugin that overrides the built-in `terminal` tool:

1. Requires LLM-provided `reason` in the tool schema
2. Validates via the Hermes adapter sidecar (`IF_AGENT_ADAPTER_SOCKET`)
3. Delegates to Hermes `terminal_tool` on ALLOW

## Install

From the repo root:

```bash
bin/intentframe-integrations integrate hermes
bin/intentframe-integrations start hermes
export IF_AGENT_ADAPTER_SOCKET=~/.intentframe/integrations/hermes/adapter.sock
```

Or manually symlink the plugin and enable it in `~/.hermes/config.yaml` (see
`integrations/hermes/README.md`).

## Dependencies

Uses `httpx` (a Hermes core dependency) to call the adapter over UDS. The plugin does not
talk to the IntentFrame bridge directly and does not need the bridge secret.
