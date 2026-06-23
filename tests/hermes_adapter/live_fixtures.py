"""Shared Hermes tool args for live adapter/plugin E2E tests."""

from __future__ import annotations

import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent.parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from hermes_tool_probes import (  # noqa: E402
    patch_replace_allow_args,
    patch_replace_block_args,
    patch_v4a_block_args,
    patch_v4a_mixed_home_delete_args,
    process_allow_args,
    process_block_args,
    write_allow_args,
    write_block_args,
)

_LIVE_MARKER = "live"

PROCESS_ALLOW_ARGS = process_allow_args()
PROCESS_BLOCK_ARGS = process_block_args()
WRITE_ALLOW_ARGS = write_allow_args(marker=_LIVE_MARKER)
WRITE_BLOCK_ARGS = write_block_args()
PATCH_ALLOW_REPLACE_ARGS = patch_replace_allow_args(marker=_LIVE_MARKER)
PATCH_BLOCK_REPLACE_ARGS = patch_replace_block_args()
PATCH_V4A_MIXED_HOME_DELETE_ARGS = patch_v4a_mixed_home_delete_args(marker=_LIVE_MARKER)
PATCH_V4A_BLOCK_ARGS = patch_v4a_block_args(marker=_LIVE_MARKER)

# Back-compat aliases
PATCH_V4A_MIXED_ALLOW_ARGS = PATCH_V4A_MIXED_HOME_DELETE_ARGS
PATCH_V4A_MIXED_ALLOW = PATCH_V4A_MIXED_HOME_DELETE_ARGS["patch"]
PATCH_V4A_BLOCK_SYSTEM_DELETE = PATCH_V4A_BLOCK_ARGS["patch"]
