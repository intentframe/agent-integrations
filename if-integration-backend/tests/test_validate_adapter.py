#!/usr/bin/env python3
"""Unit tests for ValidateOnlyAdapter."""

from __future__ import annotations

import asyncio
import sys
import unittest


class TestValidateOnlyAdapter(unittest.TestCase):
    def test_default_supported_actions(self) -> None:
        from if_security_backend.executor_pack.validate_adapter import ValidateOnlyAdapter

        adapter = ValidateOnlyAdapter()
        self.assertEqual(adapter.supported_actions(), ["RUN_COMMAND", "WRITE_HOST_FILE", "DELETE_HOST_FILE"])

    def test_pack_options_supported_actions(self) -> None:
        from if_security_backend.executor_pack.validate_adapter import ValidateOnlyAdapter

        adapter = ValidateOnlyAdapter(
            pack_options={
                "validate_only": {
                    "supported_actions": ["RUN_COMMAND", "WRITE_HOST_FILE"],
                }
            }
        )
        self.assertEqual(
            adapter.supported_actions(),
            ["RUN_COMMAND", "WRITE_HOST_FILE"],
        )
        self.assertEqual(
            adapter.manifest().supported_actions,
            ["RUN_COMMAND", "WRITE_HOST_FILE"],
        )

    def test_execute_run_command(self) -> None:
        from if_security_backend.executor_pack.validate_adapter import ValidateOnlyAdapter

        adapter = ValidateOnlyAdapter()
        result = asyncio.run(
            adapter.execute("RUN_COMMAND", {"command": "echo ok", "reason": "test"})
        )
        self.assertTrue(result.success)
        assert result.data is not None
        self.assertTrue(result.data.get("validated_only"))
        self.assertEqual(result.data.get("action"), "RUN_COMMAND")
        self.assertEqual(result.data.get("target"), "echo ok")

    def test_execute_write_host_file(self) -> None:
        from if_security_backend.executor_pack.validate_adapter import ValidateOnlyAdapter

        adapter = ValidateOnlyAdapter(
            pack_options={
                "validate_only": {
                    "supported_actions": ["WRITE_HOST_FILE"],
                }
            }
        )
        result = asyncio.run(
            adapter.execute(
                "WRITE_HOST_FILE",
                {"path": "~/notes.txt", "content": "hello", "reason": "test"},
            )
        )
        self.assertTrue(result.success)
        assert result.data is not None
        self.assertTrue(result.data.get("validated_only"))
        self.assertEqual(result.data.get("action"), "WRITE_HOST_FILE")
        self.assertEqual(result.data.get("target"), "~/notes.txt")

    def test_execute_delete_host_file(self) -> None:
        from if_security_backend.executor_pack.validate_adapter import ValidateOnlyAdapter

        adapter = ValidateOnlyAdapter()
        result = asyncio.run(
            adapter.execute(
                "DELETE_HOST_FILE",
                {"path": "~/notes.txt", "reason": "test"},
            )
        )
        self.assertTrue(result.success)
        assert result.data is not None
        self.assertTrue(result.data.get("validated_only"))
        self.assertEqual(result.data.get("action"), "DELETE_HOST_FILE")
        self.assertEqual(result.data.get("target"), "~/notes.txt")

    def test_invalid_pack_options(self) -> None:
        from if_security_backend.executor_pack.validate_adapter import ValidateOnlyAdapter

        with self.assertRaises(ValueError):
            ValidateOnlyAdapter(pack_options={"validate_only": []})


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
