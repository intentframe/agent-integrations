"""HTTP-over-UDS bridge: Authorization bearer → Actor handshake/submit → IntentFrame."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any

from intentframe_core.types import AgentCapabilities
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from if_security_backend.bridge.actor_pool import BridgeActorPool, HandshakeRequiredError
from if_security_backend.bridge.config import (
    BridgeAgentConfig,
    BridgeConfigError,
    load_bridge_agents,
    resolve_agent_by_secret,
)
from if_security_backend.runtime.health import core_healthy
from if_security_backend.runtime.paths import run_dir

_RESERVED = frozenset({"action", "target", "reason", "display_subject"})


def _core_socket() -> str:
    return os.environ.get(
        "INTENTFRAME_CORE_SOCKET",
        str(run_dir() / "intentframe.sock"),
    )


def _extract_bearer(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    key = request.headers.get("x-intentframe-agent-key")
    return key.strip() if key else None


def _authenticate(request: Request, agents: dict[str, BridgeAgentConfig]) -> BridgeAgentConfig | None:
    token = _extract_bearer(request)
    if not token:
        return None
    return resolve_agent_by_secret(token, agents)


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


def _parse_capabilities(body: dict[str, Any], agent: BridgeAgentConfig) -> AgentCapabilities:
    """Build AgentCapabilities from optional client body + bridge registry defaults."""
    defaults = BridgeActorPool.default_capabilities(agent)

    agent_type = body.get("agent_type", defaults.agent_type)
    if not isinstance(agent_type, str) or not agent_type.strip():
        raise ValueError("agent_type must be a non-empty string")

    description = body.get("description", defaults.description)
    if description is not None and not isinstance(description, str):
        raise ValueError("description must be a string")

    action_types_raw = body.get("action_types")
    if action_types_raw is None:
        action_types = list(defaults.action_types)
    else:
        if not isinstance(action_types_raw, list) or not action_types_raw:
            raise ValueError("action_types must be a non-empty list of strings")
        action_types = [str(a) for a in action_types_raw]
        allowed = set(agent.action_types)
        unknown = [a for a in action_types if a not in allowed]
        if unknown:
            raise ValueError(
                f"action_types not enabled for agent {agent.agent_id!r}: {unknown!r}"
            )

    capabilities_raw = body.get("capabilities", defaults.capabilities)
    if not isinstance(capabilities_raw, list):
        raise ValueError("capabilities must be a list of strings")
    capabilities = [str(c) for c in capabilities_raw]

    resource_needs_raw = body.get("resource_needs", defaults.resource_needs)
    if not isinstance(resource_needs_raw, list):
        raise ValueError("resource_needs must be a list of strings")
    resource_needs = [str(r) for r in resource_needs_raw]

    version = body.get("version", defaults.version)
    if not isinstance(version, str):
        raise ValueError("version must be a string")

    author = body.get("author", defaults.author)
    if author is not None and not isinstance(author, str):
        raise ValueError("author must be a string")

    return AgentCapabilities(
        agent_type=agent_type.strip(),
        description=str(description or ""),
        action_types=action_types,
        capabilities=capabilities,
        resource_needs=resource_needs,
        version=version,
        author=str(author or ""),
    )


def _normalize_request(body: dict[str, Any]) -> dict[str, Any]:
    action = body.get("action")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Missing required field: action")

    reason = body.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("Missing required field: reason")

    req: dict[str, Any] = {
        "action": action.strip(),
        "reason": reason.strip(),
        "target": str(body.get("target") or ""),
    }
    if display := body.get("display_subject"):
        req["display_subject"] = str(display)

    for key, value in body.items():
        if key not in _RESERVED and key not in req:
            req[key] = value

    return req


def _response_from_result(result) -> dict[str, Any]:
    data = result.data if isinstance(result.data, dict) else {}
    decision = data.get("decision")
    validated_only = bool(data.get("validated_only"))
    allowed = bool(result.success and validated_only)

    if result.success and not validated_only:
        # Real executor path (not our noop validate-only deployment).
        allowed = True

    if not result.success and decision is None:
        if isinstance(result.error, str) and result.error.startswith("Blocked:"):
            decision = "BLOCK"

    return {
        "allowed": allowed,
        "success": bool(result.success),
        "validated_only": validated_only,
        "decision": decision,
        "error": result.error,
        "data": data,
        "execution_id": getattr(result, "execution_id", None),
    }


def create_app(*, config_path=None) -> Starlette:
    try:
        agents = load_bridge_agents(config_path)
    except BridgeConfigError as exc:
        raise RuntimeError(str(exc)) from exc

    pool = BridgeActorPool(core_socket=_core_socket())

    async def health(_request: Request) -> JSONResponse:
        return JSONResponse(
            {
                "status": "ok" if core_healthy() else "degraded",
                "core_healthy": core_healthy(),
                "bridge": "intentframe-validate-bridge",
            }
        )

    async def handshake(request: Request) -> JSONResponse:
        agent = _authenticate(request, agents)
        if agent is None:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        if not core_healthy():
            return JSONResponse(
                {"error": "IntentFrame core is not healthy"},
                status_code=503,
            )

        try:
            body = await _read_json_object(request)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        try:
            caps = _parse_capabilities(body, agent)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        try:
            ctx = await pool.handshake(agent, caps)
        except Exception as exc:
            return JSONResponse({"error": f"Bridge handshake failed: {exc}"}, status_code=502)

        payload = ctx.model_dump(mode="json")
        payload["agent_id"] = agent.agent_id
        payload["user_id"] = agent.user_id
        return JSONResponse(payload)

    async def validate(request: Request) -> JSONResponse:
        agent = _authenticate(request, agents)
        if agent is None:
            return JSONResponse({"error": "Unauthorized"}, status_code=401)

        try:
            body = await _read_json_object(request)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        try:
            intent_req = _normalize_request(body)
        except ValueError as exc:
            return JSONResponse({"error": str(exc)}, status_code=400)

        if intent_req["action"] not in agent.action_types:
            return JSONResponse(
                {
                    "error": (
                        f"Action {intent_req['action']!r} not enabled for agent "
                        f"{agent.agent_id!r}"
                    ),
                },
                status_code=403,
            )

        if not core_healthy():
            return JSONResponse(
                {"error": "IntentFrame core is not healthy"},
                status_code=503,
            )

        try:
            result = await pool.submit(agent, intent_req)
        except HandshakeRequiredError as exc:
            return JSONResponse({"error": str(exc)}, status_code=412)
        except Exception as exc:
            return JSONResponse({"error": f"Bridge submit failed: {exc}"}, status_code=502)

        payload = _response_from_result(result)
        payload["agent_id"] = agent.agent_id
        payload["user_id"] = agent.user_id
        return JSONResponse(payload)

    @asynccontextmanager
    async def lifespan(_app: Starlette):
        yield
        await pool.close()

    return Starlette(
        routes=[
            Route("/health", health, methods=["GET"]),
            Route("/handshake", handshake, methods=["POST"]),
            Route("/validate", validate, methods=["POST"]),
        ],
        lifespan=lifespan,
    )
