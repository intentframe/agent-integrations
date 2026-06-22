#!/usr/bin/env python3
"""Unit tests for /v1/toolsets contract (no network)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from toolsets_contract import (  # noqa: E402
    assert_intentframe_gate_toolsets_surface,
    format_toolsets_snapshot,
    parse_toolsets_response,
    TOOLSET_TOOL_EXPECTATIONS,
)


def _toolsets_body() -> dict[str, object]:
    data: list[dict[str, object]] = []
    for name, tools in TOOLSET_TOOL_EXPECTATIONS.items():
        data.append(
            {
                "name": name,
                "label": name,
                "description": "",
                "enabled": True,
                "configured": True,
                "tools": sorted(tools),
            }
        )
    # Extra enabled toolsets implied by hermes-api-server default composite.
    data.extend(
        [
            {
                "name": "web",
                "enabled": True,
                "configured": True,
                "tools": ["web_extract", "web_search"],
            },
            {
                "name": "browser",
                "enabled": True,
                "configured": False,
                "tools": [
                    "browser_back",
                    "browser_click",
                    "browser_console",
                    "browser_cdp",
                    "browser_dialog",
                    "browser_get_images",
                    "browser_navigate",
                    "browser_press",
                    "browser_scroll",
                    "browser_snapshot",
                    "browser_type",
                    "browser_vision",
                    "web_search",
                ],
            },
            {
                "name": "todo",
                "enabled": True,
                "configured": False,
                "tools": ["todo"],
            },
            {
                "name": "memory",
                "enabled": True,
                "configured": False,
                "tools": ["memory"],
            },
            {
                "name": "session_search",
                "enabled": True,
                "configured": False,
                "tools": ["session_search"],
            },
            {
                "name": "delegation",
                "enabled": True,
                "configured": False,
                "tools": ["delegate_task"],
            },
            {
                "name": "cronjob",
                "enabled": True,
                "configured": False,
                "tools": ["cronjob"],
            },
            {
                "name": "image_gen",
                "enabled": True,
                "configured": False,
                "tools": ["image_generate"],
            },
            {
                "name": "moa",
                "enabled": False,
                "configured": False,
                "tools": ["mixture_of_agents"],
            },
        ]
    )
    return {
        "object": "list",
        "platform": "api_server",
        "data": data,
    }


class TestToolsetsContract(unittest.TestCase):
    def test_parse_toolsets_response(self) -> None:
        snapshot = parse_toolsets_response(_toolsets_body())
        self.assertEqual(snapshot.platform, "api_server")
        self.assertIn("terminal", snapshot.enabled_tool_names)
        self.assertIn("vision_analyze", snapshot.enabled_tool_names)
        self.assertIn("execute_code", snapshot.enabled_tool_names)

    def test_assert_surface_passes_fixture(self) -> None:
        snapshot = assert_intentframe_gate_toolsets_surface(_toolsets_body())
        self.assertIn("terminal", snapshot.by_name())

    def test_assert_fails_when_terminal_disabled(self) -> None:
        body = _toolsets_body()
        for item in body["data"]:
            if item.get("name") == "terminal":
                item["enabled"] = False
        with self.assertRaises(AssertionError):
            assert_intentframe_gate_toolsets_surface(body)

    def test_assert_fails_when_distractor_missing(self) -> None:
        body = _toolsets_body()
        body["data"] = [
            item for item in body["data"]
            if item.get("name") != "vision"
        ]
        with self.assertRaises(AssertionError):
            assert_intentframe_gate_toolsets_surface(body)

    def test_format_snapshot(self) -> None:
        snapshot = parse_toolsets_response(_toolsets_body())
        text = format_toolsets_snapshot(snapshot)
        self.assertIn("terminal:", text)
        self.assertIn("vision_analyze", text)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
