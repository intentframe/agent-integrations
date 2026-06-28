# IntentFrame Control Plane

Operator admin UI for IntentFrame agent integrations. Runs **outside Hermes** on port **9720**.

## Port registry

| Surface | Owner | Default |
|---------|-------|---------|
| IntentFrame Control Plane | IntentFrame | `http://127.0.0.1:9720` |
| IntentFrame enforcement | IntentFrame | UDS (`~/.intentframe/backend/bridge.sock`, adapter socket) |
| Hermes dashboard | Hermes | `http://127.0.0.1:9119/chat` |
| Hermes API server | Hermes | `8642` |

## Lifecycle (separate from enforcement)

```bash
intentframe-integrations control-plane start
intentframe-integrations control-plane stop
intentframe-integrations control-plane status
intentframe-integrations control-plane serve   # foreground dev
```

- `up hermes` / `stop` manage the **enforcement stack only** (backend, adapter, gateway).
- `control-plane start|stop` manage the **operator UI only**.

Configuration: `~/.intentframe/.env`

```bash
INTENTFRAME_CONTROL_PLANE_HOST=127.0.0.1
INTENTFRAME_CONTROL_PLANE_PORT=9720
# optional:
INTENTFRAME_CONTROL_PLANE_TOKEN=your-local-token
```

## Install

The [install script](../scripts/install-hermes-plugin.sh) seeds IntentFrame env, builds the frontend if needed, starts the control plane, and opens `http://127.0.0.1:9720`.

Flags:

- `--no-control-plane` — skip starting the UI (CI/Docker)
- `--no-open` — do not open a browser (`--headless` implies this)

## Development

```bash
uv sync --all-packages
cd intentframe-control-plane/web && npm ci && npm run build
bin/intentframe-integrations control-plane serve
# or: npm run dev  (proxies /api → :9720)
```

## Security

- Binds to `127.0.0.1` by default.
- Optional bearer token on `/api/*` when `INTENTFRAME_CONTROL_PLANE_TOKEN` is set.
- Destructive API actions require `X-Confirm: true`.
- Do not expose on `0.0.0.0` without additional auth.

## Architecture

The React UI calls a local FastAPI server. Mutations subprocess to `intentframe-integrations` CLI commands — governance, policy, and stack lifecycle logic is not duplicated in the control plane.
