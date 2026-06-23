"""Contract helpers for Hermes provider request dumps (OpenAI upstream payload)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def request_dump_paths(hermes_home: Path) -> list[Path]:
    """Return request debug dumps written under ``$HERMES_HOME/sessions/``."""
    dump_dir = hermes_home / "sessions"
    if not dump_dir.is_dir():
        return []
    return list(dump_dir.glob("request_dump_*.json"))


def load_request_dump(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError(f"Expected request dump object, got: {raw!r}")
    return raw


def load_request_dump_body(path: Path) -> dict[str, Any]:
    dump = load_request_dump(path)
    request = dump.get("request")
    if not isinstance(request, dict):
        raise AssertionError(f"Request dump missing request object: {path}")
    body = request.get("body")
    if not isinstance(body, dict):
        raise AssertionError(f"Request dump missing request.body object: {path}")
    return body


def load_newest_request_dump(
    hermes_home: Path,
    *,
    existing: frozenset[Path] | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Return (dump path, request.body) from the first new dump after a provider call."""
    current = request_dump_paths(hermes_home)
    if existing is not None:
        new_paths = [path for path in current if path not in existing]
    else:
        new_paths = current
    if not new_paths:
        dump_dir = hermes_home / "sessions"
        raise AssertionError(
            "No new Hermes request dump found.\n"
            f"  dump_dir: {dump_dir}\n"
            "  Set HERMES_DUMP_REQUESTS=1 before gateway start and POST /v1/responses."
        )
    first_dump = min(new_paths, key=lambda path: path.stat().st_mtime)
    return first_dump, load_request_dump_body(first_dump)


def load_newest_request_dump_body(
    hermes_home: Path,
    *,
    existing: frozenset[Path] | None = None,
) -> dict[str, Any]:
    """Load ``request.body`` from the first new dump after a provider call."""
    _, body = load_newest_request_dump(hermes_home, existing=existing)
    return body


TOOLSETS_RUN_MARKER_PREFIX = "intentframe-toolsets"


def toolsets_run_marker(run_id: str) -> str:
    """Unique token for one toolsets live test run (OpenAI logs + request dumps)."""
    return f"{TOOLSETS_RUN_MARKER_PREFIX}-{run_id}"


def toolsets_llm_prompt(marker: str) -> str:
    return (
        f"Reply with exactly this single token and nothing else: {marker}. "
        "Do not call any tools."
    )


def toolsets_llm_instructions(marker: str) -> str:
    return (
        f"Automated IntentFrame toolsets integration test run_id={marker}. "
        "Do not use tools. Your entire reply must be exactly the marker token."
    )


def extract_gateway_text_output(gateway_body: dict[str, Any]) -> str:
    """Concatenate assistant text from Hermes ``POST /v1/responses`` output items."""
    parts: list[str] = []
    output = gateway_body.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return " ".join(parts).strip()


def assert_gateway_response_contains_marker(gateway_body: dict[str, Any], marker: str) -> str:
    """Assert the LLM round-trip echoed the run marker in gateway output."""
    text = extract_gateway_text_output(gateway_body)
    if marker not in text:
        raise AssertionError(
            f"Gateway response missing run marker {marker!r}.\n"
            f"  extracted_text={text!r}\n"
            f"  body: {json.dumps(gateway_body)[:2000]}"
        )
    return text


def extract_provider_user_message(body: dict[str, Any]) -> str | None:
    """Best-effort user message from a chat.completions request dump body."""
    messages = body.get("messages")
    if not isinstance(messages, list):
        return None
    for msg in reversed(messages):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            return content
    return None


def assert_provider_request_contains_marker(body: dict[str, Any], marker: str) -> None:
    """Assert the OpenAI upstream payload included the run marker in the user message."""
    user = extract_provider_user_message(body)
    if user is None or marker not in user:
        raise AssertionError(
            f"Provider request dump missing run marker {marker!r}.\n"
            f"  user_message={user!r}"
        )


def tool_reason_required(fn: dict[str, Any]) -> bool:
    """Return True when ``reason`` is a required parameter in a function schema."""
    params = fn.get("parameters")
    if not isinstance(params, dict):
        return False
    props = params.get("properties")
    if not isinstance(props, dict) or "reason" not in props:
        return False
    required = params.get("required")
    if not isinstance(required, list):
        return False
    return "reason" in required


def parse_provider_tools(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Map tool name -> function schema from chat-completions ``tools`` list."""
    tools_raw = body.get("tools")
    if not isinstance(tools_raw, list):
        return {}

    by_name: dict[str, dict[str, Any]] = {}
    for item in tools_raw:
        if not isinstance(item, dict):
            continue
        fn = item.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if isinstance(name, str) and name:
            by_name[name] = fn
    return by_name


def assert_provider_tools_surface(
    body: dict[str, Any],
    governed: frozenset[str],
    *,
    expected_model: str | None = None,
) -> None:
    """Assert provider kwargs include governed tools with required ``reason``."""
    if expected_model is not None:
        model = body.get("model")
        if model != expected_model:
            raise AssertionError(
                f"Provider model mismatch.\n"
                f"  expected: {expected_model!r}\n"
                f"  actual:   {model!r}"
            )

    by_name = parse_provider_tools(body)
    if not by_name:
        raise AssertionError(
            f"Provider request body missing tools list: {json.dumps(body)[:2000]}"
        )

    missing = sorted(governed - set(by_name))
    if missing:
        raise AssertionError(
            f"Governed tools missing from provider tools=: {missing}\n"
            f"  present: {sorted(by_name)}"
        )

    errors: list[str] = []
    for tool_name in sorted(governed):
        fn = by_name[tool_name]
        params = fn.get("parameters")
        if not isinstance(params, dict):
            errors.append(f"{tool_name}: missing parameters object")
            continue
        props = params.get("properties")
        if not isinstance(props, dict):
            errors.append(f"{tool_name}: missing properties")
            continue
        required = params.get("required")
        if not isinstance(required, list):
            required = []
        if "reason" not in props:
            errors.append(f"{tool_name}: reason not in schema properties")
        elif "reason" not in required:
            errors.append(f"{tool_name}: reason not in required")

    if errors:
        raise AssertionError(
            "Provider tools= schema mismatch:\n  " + "\n  ".join(errors)
        )


def extract_gateway_usage(body: dict[str, Any]) -> dict[str, int]:
    """Return token usage from a Hermes ``POST /v1/responses`` body."""
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return {}
    extracted: dict[str, int] = {}
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
            extracted[key] = value
    return extracted


def assert_gateway_openai_roundtrip(gateway_body: dict[str, Any]) -> dict[str, int]:
    """Assert Hermes completed a real provider round-trip (non-zero token usage)."""
    status = gateway_body.get("status")
    if status != "completed":
        raise AssertionError(
            f"Gateway response not completed.\n"
            f"  status: {status!r}\n"
            f"  body: {json.dumps(gateway_body)[:2000]}"
        )

    usage = extract_gateway_usage(gateway_body)
    total = usage.get("total_tokens", 0)
    if total <= 0:
        raise AssertionError(
            "Gateway reported zero token usage — OpenAI round-trip did not occur.\n"
            f"  usage: {usage!r}\n"
            f"  body: {json.dumps(gateway_body)[:2000]}"
        )
    return usage


def format_gateway_roundtrip_snapshot(
    gateway_body: dict[str, Any],
    *,
    provider_url: str | None = None,
    expected_model: str | None = None,
    run_marker: str | None = None,
    gateway_output_text: str | None = None,
) -> str:
    """Human-readable proof that Hermes completed an OpenAI chat.completions call."""
    usage = extract_gateway_usage(gateway_body)
    output = gateway_body.get("output")
    output_items = output if isinstance(output, list) else []
    lines = [
        "OpenAI round-trip completed (via Hermes gateway):",
    ]
    if run_marker is not None:
        lines.append(f"  run_marker={run_marker!r}")
    lines.extend(
        [
            f"  gateway_status={gateway_body.get('status')!r}",
            f"  provider_url={provider_url!r}",
        ]
    )
    if expected_model is not None:
        lines.append(f"  provider_model={expected_model!r}")
    if gateway_output_text is not None:
        lines.append(f"  gateway_output_text={gateway_output_text!r}")
    lines.extend(
        [
            f"  input_tokens={usage.get('input_tokens', 0)}",
            f"  output_tokens={usage.get('output_tokens', 0)}",
            f"  total_tokens={usage.get('total_tokens', 0)}",
            f"  output_items={len(output_items)}",
        ]
    )
    lines.append("")
    lines.append(
        "Note: Platform Logs often omit chat.completions calls when store=false "
        "(API default). Check Usage for gpt-4o-mini at this timestamp."
    )
    return "\n".join(lines)


def format_provider_tools_snapshot(
    body: dict[str, Any],
    governed: frozenset[str],
    *,
    dump_path: Path | None = None,
    run_marker: str | None = None,
) -> str:
    """Human-readable summary of ``tools=`` sent to the OpenAI provider."""
    by_name = parse_provider_tools(body)
    model = body.get("model")
    lines = [
        f"model={model!r}",
        f"tool_count={len(by_name)}",
    ]
    if run_marker is not None:
        lines.append(f"run_marker={run_marker!r}")
    if dump_path is not None:
        lines.append(f"request_dump={dump_path}")
    lines.append("")
    lines.append("tools sent to OpenAI (chat.completions tools=):")
    for name in sorted(by_name):
        fn = by_name[name]
        if name in governed:
            reason = tool_reason_required(fn)
            lines.append(f"  {name} [governed, reason_required={reason}]")
        else:
            lines.append(f"  {name}")
    governed_present = sorted(set(by_name) & governed)
    lines.extend(
        [
            "",
            "governed tools in provider payload:",
            f"  {governed_present}",
        ]
    )
    return "\n".join(lines)
