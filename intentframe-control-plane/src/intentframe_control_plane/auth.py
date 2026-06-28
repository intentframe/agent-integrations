"""Optional bearer token auth for control plane API routes."""

from __future__ import annotations

from fastapi import HTTPException, Request

from intentframe_control_plane.config import ControlPlaneSettings


def require_auth(request: Request, settings: ControlPlaneSettings) -> None:
    if not settings.token:
        return
    auth = request.headers.get("Authorization", "")
    if auth == f"Bearer {settings.token}":
        return
    raise HTTPException(status_code=401, detail="Unauthorized")


def require_confirm(request: Request) -> None:
    if request.headers.get("X-Confirm", "").lower() in {"1", "true", "yes"}:
        return
    raise HTTPException(
        status_code=400,
        detail="Destructive action requires X-Confirm: true header",
    )
