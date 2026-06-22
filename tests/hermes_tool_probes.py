"""Deterministic probe payloads for governed Hermes tools (live + gateway E2E)."""

from __future__ import annotations

# All tools listed in integrations/hermes/governance/tools.yaml
GOVERNED_TOOL_NAMES = frozenset({"terminal", "process", "write_file", "delete_file", "patch"})


def process_allow_args(*, reason: str = "Live process allow test") -> dict[str, str]:
    return {"action": "list", "reason": reason}


def process_block_args(*, reason: str = "Should block process command") -> dict[str, str]:
    return {"action": "run", "data": "sudo rm -rf /", "reason": reason}


def write_allow_args(*, marker: str, reason: str | None = None) -> dict[str, str]:
    return {
        "path": f"~/intentframe-e2e-{marker}.txt",
        "content": marker,
        "reason": reason or "Live write allow test",
    }


def write_block_args(*, reason: str = "Should block write") -> dict[str, str]:
    return {
        "path": "/etc/intentframe-e2e-block-probe",
        "content": "blocked",
        "reason": reason,
    }


def delete_allow_args(*, marker: str, reason: str | None = None) -> dict[str, str]:
    return {
        "path": f"~/intentframe-e2e-delete-{marker}.txt",
        "reason": reason or "Live delete allow test",
    }


def delete_block_args(*, reason: str = "Should block delete") -> dict[str, str]:
    return {
        "path": "/etc/intentframe-e2e-delete-block-probe",
        "reason": reason,
    }


def patch_replace_allow_args(*, marker: str, reason: str | None = None) -> dict[str, str]:
    return {
        "mode": "replace",
        "path": f"~/intentframe-e2e-patch-{marker}.txt",
        "old_string": "a",
        "new_string": marker,
        "reason": reason or "Live patch replace allow test",
    }


def patch_replace_block_args(*, reason: str = "Should block patch replace") -> dict[str, str]:
    return {
        "mode": "replace",
        "path": "/etc/intentframe-e2e-patch-block-probe",
        "old_string": "a",
        "new_string": "b",
        "reason": reason,
    }


def patch_v4a_mixed_allow_content(*, marker: str) -> str:
    keep = f"~/intentframe-e2e-patch-keep-{marker}.txt"
    drop = f"~/intentframe-e2e-patch-drop-{marker}.txt"
    return (
        "*** Begin Patch\n"
        f"*** Update File: {keep}\n"
        "@@\n"
        "-old\n"
        "+new\n"
        f"*** Delete File: {drop}\n"
        "*** End Patch"
    )


def patch_v4a_mixed_allow_args(*, marker: str, reason: str | None = None) -> dict[str, str]:
    return {
        "mode": "patch",
        "patch": patch_v4a_mixed_allow_content(marker=marker),
        "reason": reason or "Live patch V4A mixed allow test",
    }


def patch_v4a_block_content(*, marker: str) -> str:
    keep = f"~/intentframe-e2e-patch-ok-{marker}.txt"
    return (
        "*** Begin Patch\n"
        f"*** Update File: {keep}\n"
        "@@\n"
        "-old\n"
        "+new\n"
        "*** Delete File: /etc/intentframe-e2e-patch-block-probe\n"
        "*** End Patch"
    )


def patch_v4a_block_args(*, marker: str, reason: str = "Should block patch delete on system path") -> dict[str, str]:
    return {
        "mode": "patch",
        "patch": patch_v4a_block_content(marker=marker),
        "reason": reason,
    }
