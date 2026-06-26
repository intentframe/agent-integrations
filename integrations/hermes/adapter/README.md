# hermes-adapter

Per-agent sidecar for Hermes ↔ IntentFrame validate-only integration.

The Hermes plugin calls this adapter over UDS; the adapter calls the generic
IntentFrame bridge (`~/.intentframe/backend/bridge.sock`) using
`if-integration-bridge-client`.

## Run (normally via CLI)

```bash
bin/intentframe-integrations up hermes
```

Low-level (adapter only, no gateway):

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
- `POST /validate-tool` — `{ "tool": "<name>", "args": { …, "reason": "…" } }`

Governed tools and mapper kinds are defined in `../governance/tools.yaml`.
Each call maps to one or more bridge `/validate` payloads; multi-intent tools
(e.g. V4A `patch`) fail closed if any sub-intent BLOCKs.

### Example payloads

**`terminal`** → `RUN_COMMAND`:

```json
{
  "tool": "terminal",
  "args": { "command": "echo ok", "reason": "List workspace files" }
}
```

**`write_file`** → `WRITE_HOST_FILE`:

```json
{
  "tool": "write_file",
  "args": {
    "path": "~/notes.txt",
    "content": "hello",
    "reason": "Save session notes"
  }
}
```

**`patch`** (V4A) → multiple intents; delete ops map to `DELETE_HOST_FILE`; write op includes batch manifest:

```json
{
  "tool": "patch",
  "args": {
    "mode": "patch",
    "patch": "*** Begin Patch\n*** Update File: ~/a.txt\n@@\n-old\n+new\n*** Delete File: ~/b.txt\n*** End Patch",
    "reason": "Apply edits"
  }
}
```

Maps to two bridge requests. The write intent's flattened `data` includes scoped
`content` (update hunk only) plus `patch_op_index`, `patch_op_count`, and
`patch_operations` listing every op in the batch. See `mapper.py` and
[`docs/delete-host-file-validation.md`](../../../docs/delete-host-file-validation.md).
