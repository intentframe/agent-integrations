#!/usr/bin/env python3
"""Unit tests for provider request dump assertions (no network)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from provider_request_contract import (  # noqa: E402
    assert_gateway_openai_roundtrip,
    assert_provider_tools_surface,
    format_gateway_roundtrip_snapshot,
    format_provider_tools_snapshot,
    load_newest_request_dump,
    load_newest_request_dump_body,
    load_request_dump_body,
    parse_provider_tools,
    tool_reason_required,
)


def _tool(name: str, *, reason_required: bool = True) -> dict[str, object]:
    params: dict[str, object] = {
        "type": "object",
        "properties": {"command": {"type": "string"}},
        "required": ["command"],
    }
    if reason_required:
        params["properties"]["reason"] = {"type": "string"}
        params["required"] = ["command", "reason"]
    return {"type": "function", "function": {"name": name, "parameters": params}}


class ProviderRequestContractTests(unittest.TestCase):
    def test_parse_provider_tools(self) -> None:
        body = {"tools": [_tool("terminal"), _tool("process")]}
        by_name = parse_provider_tools(body)
        self.assertEqual(set(by_name), {"terminal", "process"})

    def test_assert_provider_tools_surface_passes(self) -> None:
        body = {
            "model": "gpt-4o-mini",
            "tools": [
                _tool("terminal"),
                _tool("process"),
                _tool("write_file"),
                _tool("patch"),
            ],
        }
        assert_provider_tools_surface(
            body,
            frozenset({"terminal", "process", "write_file", "patch"}),
            expected_model="gpt-4o-mini",
        )

    def test_assert_provider_tools_surface_missing_reason(self) -> None:
        body = {"tools": [_tool("terminal", reason_required=False)]}
        with self.assertRaisesRegex(AssertionError, "reason not in schema"):
            assert_provider_tools_surface(body, frozenset({"terminal"}))

    def test_load_newest_request_dump_body(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            hermes_home = Path(tmp)
            sessions = hermes_home / "sessions"
            sessions.mkdir()
            existing_path = sessions / "request_dump_old.json"
            existing_path.write_text(
                json.dumps({"request": {"body": {"tools": []}}}),
                encoding="utf-8",
            )
            new_path = sessions / "request_dump_new.json"
            new_path.write_text(
                json.dumps(
                    {
                        "request": {
                            "method": "POST",
                            "url": "https://api.openai.com/v1/chat/completions",
                            "body": {
                                "model": "gpt-4o-mini",
                                "tools": [_tool("terminal")],
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            dump_path, body = load_newest_request_dump(
                hermes_home,
                existing=frozenset({existing_path}),
            )
            self.assertEqual(dump_path, new_path)
            self.assertEqual(body["model"], "gpt-4o-mini")
            self.assertIn("terminal", parse_provider_tools(body))
            self.assertEqual(
                load_newest_request_dump_body(
                    hermes_home,
                    existing=frozenset({existing_path}),
                ),
                body,
            )

    def test_assert_gateway_openai_roundtrip_passes(self) -> None:
        body = {
            "status": "completed",
            "usage": {"input_tokens": 100, "output_tokens": 2, "total_tokens": 102},
        }
        usage = assert_gateway_openai_roundtrip(body)
        self.assertEqual(usage["total_tokens"], 102)

    def test_assert_gateway_openai_roundtrip_zero_tokens(self) -> None:
        body = {"status": "completed", "usage": {"total_tokens": 0}}
        with self.assertRaisesRegex(AssertionError, "zero token usage"):
            assert_gateway_openai_roundtrip(body)

    def test_format_gateway_roundtrip_snapshot(self) -> None:
        body = {
            "status": "completed",
            "usage": {"input_tokens": 11655, "output_tokens": 2, "total_tokens": 11657},
            "output": [{"type": "message", "content": [{"text": "OK"}]}],
        }
        text = format_gateway_roundtrip_snapshot(
            body,
            provider_url="https://api.openai.com/v1/chat/completions",
            expected_model="gpt-4o-mini",
        )
        self.assertIn("total_tokens=11657", text)
        self.assertIn("provider_url='https://api.openai.com/v1/chat/completions'", text)

    def test_format_provider_tools_snapshot(self) -> None:
        body = {
            "model": "gpt-4o-mini",
            "tools": [
                _tool("terminal"),
                _tool("execute_code", reason_required=False),
            ],
        }
        governed = frozenset({"terminal"})
        text = format_provider_tools_snapshot(
            body,
            governed,
            dump_path=Path("/tmp/dump.json"),
        )
        self.assertIn("model='gpt-4o-mini'", text)
        self.assertIn("request_dump=/tmp/dump.json", text)
        self.assertIn("terminal [governed, reason_required=True]", text)
        self.assertIn("execute_code", text)
        self.assertNotIn("execute_code [governed", text)
        self.assertIn("['terminal']", text)

    def test_tool_reason_required(self) -> None:
        fn = _tool("terminal")["function"]
        self.assertTrue(tool_reason_required(fn))
        self.assertFalse(tool_reason_required(_tool("x", reason_required=False)["function"]))

    def test_load_request_dump_body_rejects_invalid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text('{"request": {}}', encoding="utf-8")
            with self.assertRaises(AssertionError):
                load_request_dump_body(bad)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
