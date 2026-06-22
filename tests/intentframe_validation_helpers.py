"""Shared expectations for IntentFrame validate decisions in integration tests."""

from __future__ import annotations

from typing import Any


def semantic_validate_decision_allowed(body: dict[str, Any]) -> bool:
    """Validate adapter/bridge decision shape; return True if allowed else False."""
    if not isinstance(body, dict):
        raise AssertionError(f"Expected dict response, got {type(body)!r}")
    if "allowed" not in body:
        raise AssertionError(f"Missing allowed field: {body!r}")

    allowed = body["allowed"]
    if allowed is True:
        return True
    if allowed is False:
        if body.get("error"):
            return False
        agent_response = body.get("agent_response")
        if isinstance(agent_response, dict) and agent_response.get("status") in ("blocked", "error"):
            return False
        raise AssertionError(f"Blocked response missing error/agent_response: {body!r}")
    raise AssertionError(f"allowed must be boolean, got {allowed!r}")


def assert_bridge_semantic_delete(body: dict[str, Any]) -> bool:
    """Bridge DELETE_HOST_FILE validate — ALLOW or BLOCK with valid shape."""
    allowed = semantic_validate_decision_allowed(body)
    if allowed and body.get("validated_only") is not True:
        raise AssertionError(f"Allowed bridge delete missing validated_only=True: {body!r}")
    return allowed


def assert_adapter_semantic_validate(body: dict[str, Any]) -> bool:
    """Adapter validate-tool — ALLOW or BLOCK with valid shape."""
    return semantic_validate_decision_allowed(body)
