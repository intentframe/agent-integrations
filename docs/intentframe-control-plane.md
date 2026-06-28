# IntentFrame Control Plane

Operator admin UI for IntentFrame agent integrations. Runs **outside Hermes** on port **9720**.

Hermes chat (`http://127.0.0.1:9119/chat`) and the control plane are **separate processes and ports**. The control plane manages governance, policy, stack lifecycle, and audit logs; Hermes is where you chat with the agent.

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
intentframe-integrations control-plane serve   # foreground dev (no PID file)
```

- `up hermes` / `stop` manage the **enforcement stack only** (backend, adapter, gateway).
- `control-plane start|stop` manage the **operator UI only**.
- `control-plane stop` does **not** stop Hermes or the enforcement stack.

Configuration: `~/.intentframe/.env`

```bash
INTENTFRAME_CONTROL_PLANE_HOST=127.0.0.1
INTENTFRAME_CONTROL_PLANE_PORT=9720
# optional:
INTENTFRAME_CONTROL_PLANE_TOKEN=your-local-token
# Docker / LAN bind (requires explicit opt-in):
INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE=1
```

## How the frontend is served

There is no separate nginx or Vite server in production. One **uvicorn** process serves both the React UI and the JSON API on the same port.

```text
Browser → :9720 → uvicorn (FastAPI)
                    ├── GET /              → static/index.html (React SPA)
                    ├── GET /assets/*      → built JS/CSS
                    ├── GET /governance    → index.html (SPA fallback for deep links)
                    └── GET /api/*         → JSON backend
```

The React app calls same-origin APIs (`fetch("/api/status")`, etc.) — no CORS, no second port.

### Static build (git-tracked)

Vite builds `intentframe-control-plane/web/` into:

```text
intentframe-control-plane/src/intentframe_control_plane/static/
```

That directory is **committed to git** so installs and Docker work without Node.js. The [install script](../scripts/install-hermes-plugin.sh) runs `npm ci && npm run build` only when `static/index.html` is missing.

Contributors: after changing `web/`, run `npm run build` and commit the updated `static/` files (see [CONTRIBUTING.md](../CONTRIBUTING.md)).

### UI pages

| Route | Purpose |
|-------|---------|
| `/` (Overview) | Enforcement stack status, control plane health, start/stop stack |
| `/governance` | Enable/disable governed Hermes tools |
| `/policy` | View, upload, reload, reset policy |
| `/audit` | Tail IntentFrame server log |

Mutations subprocess to `intentframe-integrations` CLI commands — governance, policy, and stack logic is not duplicated in the control plane.

## Health checks

Health is checked differently depending on **who** is asking:

| Caller | Mechanism |
|--------|-----------|
| CLI / Docker startup (`control-plane start`, `control-plane status`) | External HTTP probe to `GET /api/health` |
| Overview UI (`GET /api/status` from inside uvicorn) | In-process: if PID file matches `os.getpid()`, healthy without HTTP |

This avoids a single-worker uvicorn deadlock where a request handler blocks waiting for a second request to the same worker.

Implementation notes:

- `/api/health` is lightweight (no nested status calls).
- External probes map bind-all hosts (`0.0.0.0`, `::`) to `127.0.0.1` for the HTTP check.
- `control-plane serve` (foreground) does not write a PID file; Overview may show control plane as not running in that dev mode.

## Install

The [install script](../scripts/install-hermes-plugin.sh) seeds IntentFrame env, uses pre-built static assets (or builds if missing), starts the control plane, and opens `http://127.0.0.1:9720`.

Flags:

- `--no-control-plane` — skip starting the UI during install (CI/Docker entrypoints start it separately)
- `--no-open` — do not open a browser (`--headless` implies this)

Docker test harness: installer uses `--no-control-plane`; [entrypoint.sh](../tests/docker/entrypoint.sh) seeds `0.0.0.0:9720` config and starts the control plane after install. See [tests/docker/README.md](../tests/docker/README.md).

## Development

```bash
uv sync --all-packages
cd intentframe-control-plane/web && npm ci && npm run build
bin/intentframe-integrations control-plane serve
# or: npm run dev  (Vite :5173, proxies /api → :9720)
```

Unit tests:

```bash
uv run --package intentframe-control-plane python tests/intentframe_control_plane/test_lifecycle.py
uv run --package intentframe-control-plane python tests/intentframe_control_plane/test_read_models.py
uv run --package intentframe-control-plane python tests/intentframe_control_plane/test_server.py
```

Local Docker smoke (no full Hermes install):

```bash
bash tests/docker/test_control_plane_smoke.sh
```

## Security

- Binds to `127.0.0.1` by default.
- Optional bearer token on `/api/*` when `INTENTFRAME_CONTROL_PLANE_TOKEN` is set (`/api/health` and `/api/config` are exempt).
- Destructive API actions require `X-Confirm: true`.
- Do not expose on `0.0.0.0` without `INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE=1` and additional auth.

## Architecture

The React UI calls a local FastAPI server. Read endpoints use direct file/PID reads ([`read_models.py`](../intentframe-control-plane/src/intentframe_control_plane/read_models.py)) to avoid subprocess side effects. Write endpoints delegate to `intentframe-integrations` via [`cli_runner.py`](../intentframe-control-plane/src/intentframe_control_plane/cli_runner.py).

State lives under `~/.intentframe/` (never `~/.hermes/`).
