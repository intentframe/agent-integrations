"""Hermes gateway HTTP client for /v1/responses E2E assertions."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

_TESTS_DIR = Path(__file__).resolve().parent.parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(_TESTS_DIR))

from hermes_tool_probes import (  # noqa: E402
    patch_replace_allow_args,
    patch_replace_block_args,
    patch_v4a_block_args,
    patch_v4a_mixed_home_delete_args,
    seed_patch_replace_target,
    write_block_args,
)

# Harmless command that policy blocks via the `sudo` pattern (no destructive shell action).
BLOCK_COMMAND = "sudo echo intentframe-e2e-block-probe"
BLOCK_REASON = "IntentFrame E2E block test"


@dataclass(frozen=True)
class ToolCall:
    name: str
    call_id: str | None
    arguments: dict[str, Any]
    output: str


@dataclass(frozen=True)
class TerminalCall:
    call_id: str | None
    arguments: dict[str, Any]
    output: str


def extract_tool_calls(body: dict[str, Any], *, tool_name: str) -> list[ToolCall]:
    output = body.get("output")
    if not isinstance(output, list):
        return []

    calls: dict[str, ToolCall] = {}
    order: list[str] = []

    for item in output:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        if item_type == "function_call" and item.get("name") == tool_name:
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
            calls[key] = ToolCall(
                name=tool_name,
                call_id=call_id,
                arguments=arguments,
                output="",
            )
            order.append(key)
        elif item_type == "function_call_output":
            call_id = item.get("call_id")
            if isinstance(call_id, str) and call_id in calls:
                output_text = item.get("output", "")
                calls[call_id] = ToolCall(
                    name=calls[call_id].name,
                    call_id=call_id,
                    arguments=calls[call_id].arguments,
                    output=output_text if isinstance(output_text, str) else json.dumps(output_text),
                )

    return [calls[key] for key in order if key in calls]


def extract_terminal_calls(body: dict[str, Any]) -> list[TerminalCall]:
    return [
        TerminalCall(call_id=call.call_id, arguments=call.arguments, output=call.output)
        for call in extract_tool_calls(body, tool_name="terminal")
    ]


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


def get_toolsets(*, host: str, port: int, api_key: str) -> dict[str, Any]:
    url = f"http://{host}:{port}/v1/toolsets"
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        if not isinstance(body, dict):
            raise AssertionError(f"Expected toolsets object, got: {body!r}")
        return body


def assert_intentframe_gate_toolsets(body: dict[str, Any]) -> None:
    from toolsets_contract import assert_intentframe_gate_toolsets_surface

    assert_intentframe_gate_toolsets_surface(body)


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


def _semantic_tool_output_allowed(output: str) -> bool:
    """Return True when tool output is an allow-like decision, False when blocked."""
    if _looks_blocked(output):
        return False
    parsed = _parse_tool_output_json(output)
    status = parsed.get("status")
    if status == "ok":
        return True
    if status == "blocked":
        return False
    raise AssertionError(f"Unrecognized semantic tool output: {output!r}")


def _parse_tool_output_json(output: str) -> dict[str, Any]:
    try:
        parsed = json.loads(output)
    except json.JSONDecodeError as exc:
        raise AssertionError(f"Expected JSON tool output, got: {output!r}") from exc
    if not isinstance(parsed, dict):
        raise AssertionError(f"Expected JSON object tool output, got: {output!r}")
    return parsed


def _assert_terminal_blocked_output(output: str) -> dict[str, Any]:
    """Terminal blocks must match Hermes terminal_tool contract (exit_code -1)."""
    body = _parse_tool_output_json(output)
    exit_code = body.get("exit_code")
    if exit_code != -1:
        raise AssertionError(
            f"Expected terminal block exit_code=-1, got {exit_code!r} in {output!r}"
        )
    status = body.get("status")
    if status not in {"blocked", "error"}:
        raise AssertionError(
            f"Expected terminal block status blocked/error, got {status!r} in {output!r}"
        )
    if not body.get("error"):
        raise AssertionError(f"Expected terminal block error message in {output!r}")
    return body


def assert_block_response(body: dict[str, Any]) -> TerminalCall:
    calls = extract_terminal_calls(body)
    if not calls:
        raise AssertionError(f"No terminal function_call in block response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    command = str(call.arguments.get("command", "")).lower()
    if "sudo" not in command:
        raise AssertionError(f"Block test command unexpected: {command!r}")

    _assert_terminal_blocked_output(call.output)
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


def assert_write_file_allow(body: dict[str, Any], *, marker: str) -> ToolCall:
    calls = extract_tool_calls(body, tool_name="write_file")
    if not calls:
        raise AssertionError(f"No write_file function_call in response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    path = str(call.arguments.get("path", ""))
    content = str(call.arguments.get("content", ""))
    if marker not in path and marker not in content and marker not in call.output:
        raise AssertionError(
            f"Allow test missing marker {marker!r} in path={path!r} content={content!r} "
            f"output={call.output!r}"
        )
    if _looks_blocked(call.output):
        raise AssertionError(f"Expected allow but got blocked output: {call.output!r}")
    return call


def assert_write_file_block(body: dict[str, Any]) -> ToolCall:
    calls = extract_tool_calls(body, tool_name="write_file")
    if not calls:
        raise AssertionError(f"No write_file function_call in block response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    path = str(call.arguments.get("path", ""))
    if not path.startswith("/etc/"):
        raise AssertionError(f"Block test path unexpected: {path!r}")
    if not _looks_blocked(call.output):
        raise AssertionError(f"Expected blocked tool output, got: {call.output!r}")
    return call


def run_write_file_allow_with_retries(
    *,
    host: str,
    port: int,
    api_key: str,
    marker: str,
    attempts: int = 3,
) -> ToolCall:
    from cli_runner import step

    path = f"~/intentframe-e2e-{marker}.txt"
    instructions = (
        "You are running an automated integration test. "
        "You MUST call the write_file tool exactly once and no other tools."
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        step(f"POST /v1/responses write_file ALLOW (attempt {attempt}/{attempts})")
        prompt = (
            f"Call the write_file tool exactly once with path: {path}, "
            f"content: '{marker}', and reason: 'IntentFrame E2E write allow {attempt}'. "
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
            return assert_write_file_allow(body, marker=marker)
        except (AssertionError, RuntimeError) as exc:
            last_error = exc
    raise AssertionError(f"write_file allow test failed after {attempts} attempts: {last_error}") from last_error


def run_write_file_block_once(*, host: str, port: int, api_key: str) -> ToolCall:
    from cli_runner import step

    step("POST /v1/responses write_file BLOCK (disallowed /etc path)")
    args = write_block_args(reason="IntentFrame E2E write block test")
    path = args["path"]
    instructions = (
        "You are running an automated integration test. "
        "You MUST call the write_file tool exactly once and no other tools. "
        f"The path argument MUST remain exactly {path}. "
        "Do NOT rewrite the path to ~, $HOME, /tmp, or any other location. "
        "Do NOT make a second write_file call if the first is blocked."
    )
    prompt = (
        "Call the write_file tool exactly once with these arguments (copy path verbatim):\n"
        f"- path: {path}\n"
        f"- content: {args['content']!r}\n"
        f"- reason: {args['reason']!r}\n"
        f"\nThe path MUST stay {path}. Do not change it.\n"
        "Do not explain; just run the tool once."
    )
    body = post_responses(
        host=host,
        port=port,
        api_key=api_key,
        prompt=prompt,
        instructions=instructions,
    )
    return assert_write_file_block(body)


def _single_tool_instructions(tool_name: str) -> str:
    return (
        "You are running an automated integration test. "
        f"You MUST call the {tool_name} tool exactly once and no other tools."
    )


def _format_tool_prompt(tool_name: str, args: dict[str, str], *, attempt: int | None = None) -> str:
    lines = [f"Call the {tool_name} tool exactly once with these arguments:"]
    for key, value in args.items():
        if key == "patch":
            lines.append(f'- {key}: copy this multiline string verbatim (do not edit paths):\n\n{value}')
        else:
            lines.append(f"- {key}: {value!r}")
    if attempt is not None:
        lines.append(f"(attempt {attempt})")
    lines.append("Do not explain; just run the tool.")
    return "\n".join(lines)


def _patch_text(call: ToolCall) -> str:
    return str(call.arguments.get("patch", ""))


def assert_patch_replace_allow(body: dict[str, Any], *, marker: str) -> ToolCall:
    calls = extract_tool_calls(body, tool_name="patch")
    if not calls:
        raise AssertionError(f"No patch function_call in response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    mode = str(call.arguments.get("mode", ""))
    path = str(call.arguments.get("path", ""))
    if mode != "replace":
        raise AssertionError(f"Expected patch mode 'replace', got: {call.arguments!r}")
    if marker not in path:
        raise AssertionError(
            f"Allow test missing marker {marker!r} in path={path!r} output={call.output!r}"
        )
    if _looks_blocked(call.output):
        raise AssertionError(f"Expected allow but got blocked output: {call.output!r}")
    return call


def assert_patch_replace_block(body: dict[str, Any]) -> ToolCall:
    calls = extract_tool_calls(body, tool_name="patch")
    if not calls:
        raise AssertionError(f"No patch function_call in block response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    path = str(call.arguments.get("path", ""))
    if not path.startswith("/etc/"):
        raise AssertionError(f"Block test path unexpected: {path!r}")
    if not _looks_blocked(call.output):
        raise AssertionError(f"Expected blocked tool output, got: {call.output!r}")
    return call


def assert_patch_v4a_mixed_home_delete_semantic(body: dict[str, Any], *, marker: str) -> ToolCall:
    """V4A home write+delete — valid IntentFrame decision (ALLOW or BLOCK)."""
    calls = extract_tool_calls(body, tool_name="patch")
    if not calls:
        raise AssertionError(f"No patch function_call in response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    if str(call.arguments.get("mode", "")) != "patch":
        raise AssertionError(f"Expected patch mode 'patch', got: {call.arguments!r}")

    keep = f"intentframe-e2e-patch-keep-{marker}"
    drop = f"intentframe-e2e-patch-drop-{marker}"
    patch_text = _patch_text(call)
    if keep not in patch_text or drop not in patch_text:
        raise AssertionError(
            f"V4A home-delete semantic test missing paths keep={keep!r} drop={drop!r} patch={patch_text!r}"
        )
    if "Update File" not in patch_text or "Delete File" not in patch_text:
        raise AssertionError(f"Expected mixed V4A update+delete, got: {patch_text!r}")
    _semantic_tool_output_allowed(call.output)
    return call


def assert_patch_v4a_mixed_home_delete_guardian_block(body: dict[str, Any], *, marker: str) -> ToolCall:
    """Backward-compatible alias for assert_patch_v4a_mixed_home_delete_semantic."""
    return assert_patch_v4a_mixed_home_delete_semantic(body, marker=marker)


def assert_patch_v4a_mixed_allow(body: dict[str, Any], *, marker: str) -> ToolCall:
    """Backward-compatible alias for assert_patch_v4a_mixed_home_delete_semantic."""
    return assert_patch_v4a_mixed_home_delete_semantic(body, marker=marker)


def assert_patch_v4a_mixed_block(body: dict[str, Any]) -> ToolCall:
    calls = extract_tool_calls(body, tool_name="patch")
    if not calls:
        raise AssertionError(f"No patch function_call in block response: {json.dumps(body)[:2000]}")

    call = calls[-1]
    if str(call.arguments.get("mode", "")) != "patch":
        raise AssertionError(f"Expected patch mode 'patch', got: {call.arguments!r}")

    patch_text = _patch_text(call)
    if "/etc/intentframe-e2e-patch-block-probe" not in patch_text:
        raise AssertionError(f"V4A block test missing /etc delete path in patch={patch_text!r}")
    if "Delete File" not in patch_text:
        raise AssertionError(f"Expected V4A delete operation, got: {patch_text!r}")
    if not _looks_blocked(call.output):
        raise AssertionError(f"Expected blocked tool output, got: {call.output!r}")
    return call


def run_patch_replace_allow_with_retries(
    *,
    host: str,
    port: int,
    api_key: str,
    marker: str,
    sandbox_home: Path,
    attempts: int = 3,
) -> ToolCall:
    from cli_runner import step

    instructions = _single_tool_instructions("patch")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        step(f"POST /v1/responses patch replace ALLOW (attempt {attempt}/{attempts})")
        seed_patch_replace_target(sandbox_home, marker)
        args = patch_replace_allow_args(
            marker=marker,
            reason=f"IntentFrame E2E patch replace allow {attempt}",
        )
        try:
            body = post_responses(
                host=host,
                port=port,
                api_key=api_key,
                prompt=_format_tool_prompt("patch", args, attempt=attempt),
                instructions=instructions,
            )
            return assert_patch_replace_allow(body, marker=marker)
        except (AssertionError, RuntimeError) as exc:
            last_error = exc
    raise AssertionError(f"patch replace allow test failed after {attempts} attempts: {last_error}") from last_error


def run_patch_replace_block_once(*, host: str, port: int, api_key: str) -> ToolCall:
    from cli_runner import step

    step("POST /v1/responses patch replace BLOCK (disallowed /etc path)")
    args = patch_replace_block_args(reason="IntentFrame E2E patch replace block test")
    path = args["path"]
    instructions = (
        "You are running an automated integration test. "
        "You MUST call the patch tool exactly once and no other tools. "
        f"The path argument MUST remain exactly {path}. "
        "Do NOT rewrite the path to ~, $HOME, /tmp, or any other location. "
        "Do NOT make a second patch call if the first is blocked."
    )
    prompt = (
        "Call the patch tool exactly once with these arguments (copy path verbatim):\n"
        f"- mode: {args['mode']!r}\n"
        f"- path: {path}\n"
        f"- old_string: {args['old_string']!r}\n"
        f"- new_string: {args['new_string']!r}\n"
        f"- reason: {args['reason']!r}\n"
        f"\nThe path MUST stay {path}. Do not change it.\n"
        "Do not explain; just run the tool once."
    )
    body = post_responses(
        host=host,
        port=port,
        api_key=api_key,
        prompt=prompt,
        instructions=instructions,
    )
    return assert_patch_replace_block(body)


def run_patch_v4a_mixed_home_delete_semantic_with_retries(
    *,
    host: str,
    port: int,
    api_key: str,
    marker: str,
    attempts: int = 5,
) -> ToolCall:
    from cli_runner import step

    instructions = (
        _single_tool_instructions("patch")
        + " The patch field must include both an Update File and a Delete File section."
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        step(
            f"POST /v1/responses patch V4A mixed home-delete semantic "
            f"(attempt {attempt}/{attempts})"
        )
        args = patch_v4a_mixed_home_delete_args(
            marker=marker,
            reason=f"IntentFrame E2E patch V4A mixed home-delete semantic {attempt}",
        )
        try:
            body = post_responses(
                host=host,
                port=port,
                api_key=api_key,
                prompt=_format_tool_prompt("patch", args, attempt=attempt),
                instructions=instructions,
            )
            return assert_patch_v4a_mixed_home_delete_semantic(body, marker=marker)
        except (AssertionError, RuntimeError) as exc:
            last_error = exc
    raise AssertionError(
        f"patch V4A mixed home-delete semantic test failed after {attempts} attempts: {last_error}"
    ) from last_error


def run_patch_v4a_mixed_home_delete_guardian_block_with_retries(
    *,
    host: str,
    port: int,
    api_key: str,
    marker: str,
    attempts: int = 5,
) -> ToolCall:
    """Backward-compatible alias for run_patch_v4a_mixed_home_delete_semantic_with_retries."""
    return run_patch_v4a_mixed_home_delete_semantic_with_retries(
        host=host,
        port=port,
        api_key=api_key,
        marker=marker,
        attempts=attempts,
    )


def run_patch_v4a_mixed_allow_with_retries(
    *,
    host: str,
    port: int,
    api_key: str,
    marker: str,
    attempts: int = 5,
) -> ToolCall:
    """Backward-compatible alias for run_patch_v4a_mixed_home_delete_semantic_with_retries."""
    return run_patch_v4a_mixed_home_delete_semantic_with_retries(
        host=host,
        port=port,
        api_key=api_key,
        marker=marker,
        attempts=attempts,
    )


def run_patch_v4a_mixed_block_once(*, host: str, port: int, api_key: str, marker: str) -> ToolCall:
    from cli_runner import step

    step("POST /v1/responses patch V4A mixed BLOCK (/etc delete in multi-intent patch)")
    args = patch_v4a_block_args(
        marker=marker,
        reason="IntentFrame E2E patch V4A mixed block test",
    )
    patch_text = args["patch"]
    etc_delete_path = "/etc/intentframe-e2e-patch-block-probe"
    instructions = (
        "You are running an automated integration test. "
        "You MUST call the patch tool exactly once and no other tools. "
        "The patch field must include both an Update File and a Delete File section. "
        f"The Delete File path MUST remain exactly {etc_delete_path}. "
        "Copy the entire patch string verbatim; do NOT edit any paths in it. "
        "Do NOT rewrite /etc paths to ~, $HOME, /tmp, or any other location. "
        "Do NOT make a second patch call if the first is blocked."
    )
    prompt = (
        "Call the patch tool exactly once with these arguments:\n"
        f"- mode: {args['mode']!r}\n"
        f"- reason: {args['reason']!r}\n"
        "- patch: copy this multiline string verbatim (do not edit paths, "
        "especially the /etc delete):\n\n"
        f"{patch_text}\n\n"
        f"The Delete File path MUST stay {etc_delete_path}. Do not change it.\n"
        "Do not explain; just run the tool once."
    )
    body = post_responses(
        host=host,
        port=port,
        api_key=api_key,
        prompt=prompt,
        instructions=instructions,
    )
    return assert_patch_v4a_mixed_block(body)
