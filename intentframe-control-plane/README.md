# IntentFrame Control Plane

Operator admin UI for IntentFrame agent integrations. Runs separately from Hermes on port **9720**.

Full docs: [docs/intentframe-control-plane.md](../docs/intentframe-control-plane.md).

## Quick start

```bash
intentframe-integrations control-plane start
# http://127.0.0.1:9720
```

Hermes chat is separate: `hermes dashboard` → `http://127.0.0.1:9119/chat`.

## Frontend build

Source: `web/` (React + Vite + Tailwind).

Build output (git-tracked, shipped with the Python package):

```bash
cd web && npm ci && npm run build
# writes to ../src/intentframe_control_plane/static/
```

Commit updated `static/` when you change `web/`. End-user installs skip npm when `static/index.html` already exists in the integration pack.

uvicorn serves `static/` and `/api/*` from the same process — no separate frontend server in production.

## Layout

| Path | Role |
|------|------|
| `web/` | React source (dev: `npm run dev` proxies API to :9720) |
| `src/intentframe_control_plane/static/` | Vite build output (committed) |
| `src/intentframe_control_plane/server.py` | FastAPI app + SPA fallback |
| `src/intentframe_control_plane/lifecycle.py` | start/stop/status, health probes |
| `src/intentframe_control_plane/read_models.py` | Read-only status from PID files / YAML |

## Dev

```bash
uv sync --all-packages
cd web && npm ci && npm run build
bin/intentframe-integrations control-plane serve
```
