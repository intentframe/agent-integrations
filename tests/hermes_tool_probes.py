"""Deterministic probe payloads for governed Hermes tools (live + gateway E2E)."""

from __future__ import annotations


def process_allow_args(*, reason: str = "Live process allow test") -> dict[str, str]:
    return {"action": "list", "reason": reason}


def process_block_args(*, reason: str = "E2E process run probe") -> dict[str, str]:
    return {"action": "run", "data": "sudo rm -rf /", "reason": reason}


def write_allow_args(*, marker: str, reason: str | None = None) -> dict[str, str]:
    return {
        "path": f"~/intentframe-e2e-{marker}.txt",
        "content": marker,
        "reason": reason or "Live write allow test",
    }


def write_block_args(*, reason: str = "E2E write to system path probe") -> dict[str, str]:
    return {
        "path": "/etc/intentframe-e2e-block-probe",
        "content": "blocked",
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


def patch_replace_block_args(*, reason: str = "E2E patch replace system path probe") -> dict[str, str]:
    return {
        "mode": "replace",
        "path": "/etc/intentframe-e2e-patch-block-probe",
        "old_string": "a",
        "new_string": "b",
        "reason": reason,
    }


def patch_v4a_mixed_home_delete_content(*, marker: str) -> str:
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


def patch_v4a_mixed_home_delete_args(*, marker: str, reason: str | None = None) -> dict[str, str]:
    """V4A write+delete under ~/ — AE/Guardian outcome is semantic per intent."""
    return {
        "mode": "patch",
        "patch": patch_v4a_mixed_home_delete_content(marker=marker),
        "reason": reason or "E2E V4A patch update and delete under home",
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


def patch_v4a_block_args(*, marker: str, reason: str = "E2E V4A patch update home and delete system file") -> dict[str, str]:
    return {
        "mode": "patch",
        "patch": patch_v4a_block_content(marker=marker),
        "reason": reason,
    }
