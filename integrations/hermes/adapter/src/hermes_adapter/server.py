"""HTTP-over-UDS server for the Hermes adapter."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from hermes_adapter.service import ValidateService


async def _read_json_object(request: Request) -> dict[str, Any]:
    try:
        body = await request.json()
    except Exception:
        return {}
    if body is None:
        return {}
    if not isinstance(body, dict):
        raise ValueError("Body must be a JSON object")
    return body


def create_app(*, service: ValidateService | None = None) -> Starlette:
    validate_service = service or ValidateService()

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse({"status": "ok", "adapter": "hermes"})

    async def validate_tool(request: Request) -> JSONResponse:
        try:
            body = await _read_json_object(request)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        tool = body.get("tool")
        if not isinstance(tool, str) or not tool.strip():
            return JSONResponse({"error": "Missing required field: tool"}, status_code=400)

        args = body.get("args")
        if not isinstance(args, dict):
            return JSONResponse({"error": "args must be a JSON object"}, status_code=400)

        context = body.get("context")
        if context is not None and not isinstance(context, dict):
            return JSONResponse({"error": "context must be a JSON object"}, status_code=400)

        payload = validate_service.validate_tool(
            tool.strip(),
            args,
            context=context if isinstance(context, dict) else None,
        )
        return JSONResponse(payload)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        yield
        validate_service.close()

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/validate-tool", validate_tool, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
