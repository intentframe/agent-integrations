"""FastAPI control plane server and JSON API.

Serves the built React SPA from ``static/`` (same port as ``/api/*``). Vite output is
git-tracked under ``static/``; uvicorn is the only production frontend server.

Read endpoints use ``read_models`` (direct file/PID reads). Mutations subprocess to
``intentframe-integrations`` via ``cli_runner``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from intentframe_control_plane.auth import require_auth, require_confirm
from intentframe_control_plane.cli_runner import CliResult, run_cli
from intentframe_control_plane.config import (
    SERVER_LOG,
    ControlPlaneSettings,
    load_dotenv,
)
from intentframe_control_plane.lifecycle import control_plane_status
from intentframe_control_plane.read_models import (
    collect_status_dict,
    load_governance_dict,
    load_policy_dict,
    public_config_dict,
    tail_log_lines,
)

load_dotenv()

STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_HTML = STATIC_DIR / "index.html"
ASSETS_DIR = STATIC_DIR / "assets"


def _ok(data: Any = None, **extra: Any) -> JSONResponse:
    payload: dict[str, Any] = {"ok": True}
    if data is not None:
        payload["data"] = data
    payload.update(extra)
    return JSONResponse(payload)


def _err(message: str, status: int = 400, **extra: Any) -> JSONResponse:
    payload: dict[str, Any] = {"ok": False, "error": message}
    payload.update(extra)
    return JSONResponse(payload, status_code=status)


def _cli_payload(result: CliResult) -> dict[str, Any]:
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "argv": result.argv,
    }


def _run_or_error(args: list[str], *, timeout: float | None = 300.0) -> tuple[CliResult | None, JSONResponse | None]:
    try:
        result = run_cli(args, timeout=timeout)
    except RuntimeError as exc:
        return None, _err(str(exc), status=500)
    if result.returncode != 0:
        return result, _err(
            result.stderr.strip() or result.stdout.strip() or "CLI command failed",
            status=500,
            cli=_cli_payload(result),
        )
    return result, None


def _require_cli_result(
    result: CliResult | None,
    err: JSONResponse | None,
) -> tuple[CliResult | None, JSONResponse | None]:
    if err is not None:
        return None, err
    if result is None:
        return None, _err("CLI command returned no result", status=500)
    return result, None


app = FastAPI(title="IntentFrame Control Plane", version="0.2.0")


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return JSONResponse({"ok": False, "error": detail}, status_code=exc.status_code)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    if request.url.path.startswith("/api/") and request.url.path not in {"/api/health", "/api/config"}:
        settings = ControlPlaneSettings.from_env()
        require_auth(request, settings)
    return await call_next(request)


@app.get("/api/health")
async def health() -> JSONResponse:
    """Lightweight liveness for external probes (CLI startup, ``control-plane status``).

    Must not call ``control_plane_status()`` — that would HTTP-probe back into this
    process and deadlock a single-worker uvicorn.
    """
    settings = ControlPlaneSettings.from_env()
    return _ok(
        {
            "service": "intentframe-control-plane",
            "url": settings.url,
            "status": "ok",
        }
    )


@app.get("/api/config")
async def api_config() -> JSONResponse:
    return _ok(public_config_dict())


@app.get("/api/status")
async def api_status() -> JSONResponse:
    """Enforcement stack snapshot + control plane row for the Overview page."""
    data = collect_status_dict()
    cp = control_plane_status()
    data["control_plane"] = {
        "running": cp.running,
        "healthy": cp.healthy,
        "pid": cp.pid,
        "url": cp.url,
    }
    data["openai_api_key_set"] = bool(os.environ.get("OPENAI_API_KEY"))
    return _ok(data)


@app.get("/api/doctor")
async def api_doctor() -> JSONResponse:
    result, err = _run_or_error(["doctor", "hermes"])
    result, err = _require_cli_result(result, err)
    if err is not None:
        return err
    return _ok(
        {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "ok": result.returncode == 0,
        }
    )


@app.get("/api/governance")
async def api_governance_list() -> JSONResponse:
    return _ok(load_governance_dict())


@app.post("/api/governance/{tool}/enable")
async def api_governance_enable(tool: str) -> JSONResponse:
    result, err = _run_or_error(["governance", "enable", "hermes", tool])
    result, err = _require_cli_result(result, err)
    if err is not None:
        return err
    return _ok({"message": result.stdout.strip()})


@app.post("/api/governance/{tool}/disable")
async def api_governance_disable(tool: str) -> JSONResponse:
    result, err = _run_or_error(["governance", "disable", "hermes", tool])
    result, err = _require_cli_result(result, err)
    if err is not None:
        return err
    return _ok({"message": result.stdout.strip()})


@app.post("/api/governance/apply")
async def api_governance_apply() -> JSONResponse:
    stop_result, stop_err = _run_or_error(["gateway", "stop", "hermes"])
    stop_result, stop_err = _require_cli_result(stop_result, stop_err)
    if stop_err is not None:
        return stop_err
    start_result, start_err = _run_or_error(["gateway", "start", "hermes"])
    start_result, start_err = _require_cli_result(start_result, start_err)
    if start_err is not None:
        return start_err
    return _ok(
        {
            "stop": stop_result.stdout.strip(),
            "start": start_result.stdout.strip(),
        }
    )


@app.get("/api/policy")
async def api_policy_get() -> JSONResponse:
    return _ok(load_policy_dict())


@app.post("/api/policy/reload")
async def api_policy_reload() -> JSONResponse:
    result, err = _run_or_error(["policy", "reload", "hermes"])
    result, err = _require_cli_result(result, err)
    if err is not None:
        return err
    return _ok({"message": result.stdout.strip()})


@app.post("/api/policy/apply")
async def api_policy_apply(file: UploadFile = File(...)) -> JSONResponse:
    suffix = ".yaml"
    if file.filename and file.filename.endswith((".yml", ".yaml")):
        suffix = Path(file.filename).suffix
    content = await file.read()
    with tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name
    try:
        result, err = _run_or_error(["policy", "set", "hermes", tmp_path])
        result, err = _require_cli_result(result, err)
        if err is not None:
            return err
        return _ok({"message": result.stdout.strip()})
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/api/policy/reset")
async def api_policy_reset(request: Request) -> JSONResponse:
    require_confirm(request)
    result, err = _run_or_error(["policy", "reset", "hermes"])
    result, err = _require_cli_result(result, err)
    if err is not None:
        return err
    return _ok({"message": result.stdout.strip()})


@app.post("/api/stack/up")
async def api_stack_up() -> JSONResponse:
    if not os.environ.get("OPENAI_API_KEY"):
        return _err("OPENAI_API_KEY is not set", status=400)
    result, err = _run_or_error(["up", "hermes"], timeout=120.0)
    result, err = _require_cli_result(result, err)
    if err is not None:
        return err
    return _ok({"message": result.stdout.strip()})


@app.post("/api/stack/stop")
async def api_stack_stop(request: Request) -> JSONResponse:
    require_confirm(request)
    result, err = _run_or_error(["stop"])
    result, err = _require_cli_result(result, err)
    if err is not None:
        return err
    return _ok({"message": "Enforcement stack stopped (control plane still running)"})


@app.get("/api/audit/log")
async def api_audit_log(tail: int = 200) -> JSONResponse:
    tail = max(1, min(tail, 2000))
    lines = tail_log_lines(SERVER_LOG, max_lines=tail)
    return _ok({"lines": lines, "path": str(SERVER_LOG)})


# Static assets + SPA fallback (BrowserRouter deep links like /governance).
# Built by Vite into static/; committed so installs work without Node.js.
if INDEX_HTML.is_file():

    @app.get("/assets/{asset_path:path}")
    async def static_assets(asset_path: str) -> FileResponse:
        target = ASSETS_DIR / asset_path
        if not target.is_file():
            raise HTTPException(status_code=404, detail="Asset not found")
        return FileResponse(target)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        if full_path:
            candidate = STATIC_DIR / full_path
            if candidate.is_file():
                return FileResponse(candidate)
        return FileResponse(INDEX_HTML)
else:

    @app.get("/")
    async def missing_frontend() -> JSONResponse:
        return _err(
            "Control plane frontend not built. Run: cd intentframe-control-plane/web && npm ci && npm run build",
            status=503,
        )
