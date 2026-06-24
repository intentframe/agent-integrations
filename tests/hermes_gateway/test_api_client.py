#!/usr/bin/env python3
"""Unit tests for gateway api_client assertion helpers (no network)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from api_client import (  # noqa: E402
    assert_block_response,
    assert_patch_replace_allow,
    assert_patch_replace_block,
    assert_patch_v4a_mixed_block,
    assert_patch_v4a_mixed_home_delete_semantic,
)


def _response(*, tool: str, arguments: dict[str, object], output: str) -> dict[str, object]:
    return {
        "output": [
            {"type": "function_call", "name": tool, "call_id": "call-1", "arguments": json.dumps(arguments)},
            {"type": "function_call_output", "call_id": "call-1", "output": output},
        ]
    }


class TestApiClientAssertions(unittest.TestCase):
    def test_assert_terminal_block_response(self) -> None:
        body = _response(
            tool="terminal",
            arguments={"command": "sudo rm -rf /", "reason": "Should block"},
            output='{"exit_code": -1, "error": "policy", "status": "blocked"}',
        )
        assert_block_response(body)

    def test_assert_terminal_block_rejects_generic_json(self) -> None:
        body = _response(
            tool="terminal",
            arguments={"command": "sudo rm -rf /", "reason": "Should block"},
            output='{"status": "blocked", "error": "policy"}',
        )
        with self.assertRaises(AssertionError):
            assert_block_response(body)

    def test_assert_patch_replace_allow(self) -> None:
        body = _response(
            tool="patch",
            arguments={
                "mode": "replace",
                "path": "~/intentframe-e2e-patch-marker.txt",
                "old_string": "a",
                "new_string": "marker",
                "reason": "ok",
            },
            output='{"status": "ok"}',
        )
        assert_patch_replace_allow(body, marker="marker")

    def test_assert_patch_replace_block(self) -> None:
        body = _response(
            tool="patch",
            arguments={
                "mode": "replace",
                "path": "/etc/intentframe-e2e-patch-block-probe",
                "old_string": "a",
                "new_string": "b",
                "reason": "bad",
            },
            output='{"status": "blocked", "error": "policy"}',
        )
        assert_patch_replace_block(body)

    def test_assert_patch_v4a_mixed_home_delete_semantic_block(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: ~/intentframe-e2e-patch-keep-marker.txt\n"
            "*** Delete File: ~/intentframe-e2e-patch-drop-marker.txt\n"
            "*** End Patch"
        )
        body = _response(
            tool="patch",
            arguments={"mode": "patch", "patch": patch, "reason": "probe"},
            output='{"status": "blocked", "error": "policy"}',
        )
        assert_patch_v4a_mixed_home_delete_semantic(body, marker="marker")

    def test_assert_patch_v4a_mixed_home_delete_semantic_allow(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: ~/intentframe-e2e-patch-keep-marker.txt\n"
            "*** Delete File: ~/intentframe-e2e-patch-drop-marker.txt\n"
            "*** End Patch"
        )
        body = _response(
            tool="patch",
            arguments={"mode": "patch", "patch": patch, "reason": "probe"},
            output='{"status": "ok"}',
        )
        assert_patch_v4a_mixed_home_delete_semantic(body, marker="marker")

    def test_assert_patch_v4a_mixed_block(self) -> None:
        patch = (
            "*** Begin Patch\n"
            "*** Update File: ~/intentframe-e2e-patch-ok-marker.txt\n"
            "*** Delete File: /etc/intentframe-e2e-patch-block-probe\n"
            "*** End Patch"
        )
        body = _response(
            tool="patch",
            arguments={"mode": "patch", "patch": patch, "reason": "bad"},
            output='{"status": "blocked", "error": "policy"}',
        )
        assert_patch_v4a_mixed_block(body)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
