"""Hermes gateway HTTP client for /v1/responses E2E assertions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import httpx

# Harmless command that policy blocks via the `sudo` pattern (no destructive shell action).
BLOCK_COMMAND = "sudo echo intentframe-e2e-block-probe"
BLOCK_REASON = "IntentFrame E2E block test"


@dataclass(frozen=True)
class TerminalCall:
    call_id: str | None
    arguments: dict[str, Any]
    output: str


def wait_health(*, host: str, port: int, api_key: str, timeout: float = 120.0) -> None:
    from cli_runner import step

    deadline = time.monotonic() + timeout
    headers = {"Authorization": f"Bearer {api_key}"}
    url = f"http://{host}:{port}/health"
    last_error = "unknown"
    started = time.monotonic()
    next_log = started + 10.0
    step(f"Waiting for gateway health at {url} (timeout {timeout:.0f}s)")
    with httpx.Client(timeout=5.0) as client:
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_log:
                step(f"Still waiting for gateway health ({now - started:.0f}s)...")
                next_log = now + 10.0
            try:
                resp = client.get(url, headers=headers)
                if resp.status_code == 200:
                    step(f"Gateway healthy at {url} ({now - started:.1f}s)")
                    return
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
            except httpx.HTTPError as exc:
                last_error = str(exc)
            time.sleep(1.0)
    raise TimeoutError(f"Gateway health check failed at {url}: {last_error}")


def get_capabilities(*, host: str, port: int, api_key: str) -> dict[str, Any]:
    url = f"http://{host}:{port}/v1/capabilities"
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise AssertionError(f"Expected capabilities object, got: {body!r}")
        return body


def post_responses(
    *,
    host: str,
    port: int,
    api_key: str,
    prompt: str,
    instructions: str,
    timeout: float = 180.0,
) -> dict[str, Any]:
    url = f"http://{host}:{port}/v1/responses"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "hermes-agent",
        "input": prompt,
        "instructions": instructions,
        "store": False,
    }
    with httpx.Client(timeout=timeout) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"POST /v1/responses failed ({resp.status_code}): {resp.text[:2000]}")
        body = resp.json()
        if not isinstance(body, dict):
            raise AssertionError(f"Expected response object, got: {body!r}")
        return body


def extract_terminal_calls(body: dict[str, Any]) -> list[TerminalCall]:
    output = body.get("output")
    if not isinstance(output, list):
        return []

    calls: dict[str, TerminalCall] = {}
    order: list[str] = []

    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "function_call" and item.get("name") == "terminal":
            call_id = item.get("call_id")
            if not isinstance(call_id, str):
                call_id = None
            raw_args = item.get("arguments", "{}")
            if isinstance(raw_args, str):
                try:
                    arguments = json.loads(raw_args)
                except json.JSONDecodeError:
                    arguments = {"raw": raw_args}
            elif isinstance(raw_args, dict):
                arguments = raw_args
            else:
                arguments = {}
            key = call_id or f"anon-{len(order)}"
            calls[key] = TerminalCall(call_id=call_id, arguments=arguments, output="")
            order.append(key)
        elif item_type == "function_call_output":
            call_id = item.get("call_id")
            if isinstance(call_id, str) and call_id in calls:
                output_text = item.get("output", "")
                calls[call_id] = TerminalCall(
                    call_id=call_id,
                    arguments=calls[call_id].arguments,
                    output=output_text if isinstance(output_text, str) else json.dumps(output_text),
                )

    return [calls[key] for key in order if key in calls]


def assert_allow_response(body: dict[str, Any], *, marker: str) -> TerminalCall:
    calls = extract_terminal_calls(body)
    if not calls:
        raise AssertionError(f"No terminal function_call in response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    command = str(call.arguments.get("command", ""))
    if marker not in command and marker not in call.output:
        raise AssertionError(
            f"Allow test missing marker {marker!r} in command={command!r} output={call.output!r}"
        )

    if _looks_blocked(call.output):
        raise AssertionError(f"Expected allow but got blocked output: {call.output!r}")
    if marker not in call.output:
        raise AssertionError(f"Expected marker in tool output, got: {call.output!r}")
    return call


def _looks_blocked(output: str) -> bool:
    lowered = output.lower()
    compact = lowered.replace(" ", "")
    if '"status":"blocked"' in compact or '"status":blocked' in compact:
        return True
    if '"exit_code":-1' in compact or '"exit_code": -1' in lowered:
        return True
    return any(marker in lowered for marker in ("blocked", "denied", "not allowed", "policy"))


def assert_block_response(body: dict[str, Any]) -> TerminalCall:
    calls = extract_terminal_calls(body)
    if not calls:
        raise AssertionError(f"No terminal function_call in block response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    command = str(call.arguments.get("command", "")).lower()
    if "sudo" not in command:
        raise AssertionError(f"Block test command unexpected: {command!r}")

    if not _looks_blocked(call.output):
        raise AssertionError(f"Expected blocked tool output, got: {call.output!r}")
    return call


def run_allow_with_retries(
    *,
    host: str,
    port: int,
    api_key: str,
    marker: str,
    attempts: int = 3,
) -> TerminalCall:
    from cli_runner import step

    command = f"printf '{marker}'"
    instructions = (
        "You are running an automated integration test. "
        "You MUST call the terminal tool exactly once and no other tools."
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        step(f"POST /v1/responses ALLOW (attempt {attempt}/{attempts})")
        prompt = (
            f"Call the terminal tool exactly once with command: {command} "
            f"and reason: 'IntentFrame E2E allow attempt {attempt}'. "
            "Do not explain; just run the tool."
        )
        try:
            body = post_responses(
                host=host,
                port=port,
                api_key=api_key,
                prompt=prompt,
                instructions=instructions,
            )
            return assert_allow_response(body, marker=marker)
        except (AssertionError, RuntimeError) as exc:
            last_error = exc
    raise AssertionError(f"Allow test failed after {attempts} attempts: {last_error}") from last_error


def run_block_once(*, host: str, port: int, api_key: str) -> TerminalCall:
    prompt = (
        f"Call the terminal tool exactly once with command: {BLOCK_COMMAND} "
        f"and reason: '{BLOCK_REASON}'. Do not use any other tools."
    )
    instructions = (
        "You are running an automated integration test. "
        "You MUST call the terminal tool exactly once and no other tools."
    )
    body = post_responses(
        host=host,
        port=port,
        api_key=api_key,
        prompt=prompt,
        instructions=instructions,
    )
    return assert_block_response(body)
