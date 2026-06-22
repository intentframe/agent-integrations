#!/usr/bin/env python3
"""Unit tests for intentframe_validation_helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from intentframe_validation_helpers import (  # noqa: E402
    assert_adapter_semantic_validate,
    assert_bridge_semantic_delete,
    semantic_validate_decision_allowed,
)


class TestIntentFrameValidationHelpers(unittest.TestCase):
    def test_semantic_validate_allow(self) -> None:
        self.assertTrue(assert_adapter_semantic_validate({"allowed": True}))

    def test_semantic_validate_block_with_error(self) -> None:
        self.assertFalse(
            semantic_validate_decision_allowed({"allowed": False, "error": "blocked"})
        )

    def test_semantic_validate_block_with_agent_response(self) -> None:
        self.assertFalse(
            semantic_validate_decision_allowed(
                {"allowed": False, "agent_response": {"status": "blocked"}}
            )
        )

    def test_bridge_semantic_allow_requires_validated_only(self) -> None:
        self.assertTrue(
            assert_bridge_semantic_delete({"allowed": True, "validated_only": True})
        )

    def test_bridge_semantic_allow_rejects_missing_validated_only(self) -> None:
        with self.assertRaises(AssertionError):
            assert_bridge_semantic_delete({"allowed": True})


if __name__ == "__main__":
    raise SystemExit(unittest.main())
