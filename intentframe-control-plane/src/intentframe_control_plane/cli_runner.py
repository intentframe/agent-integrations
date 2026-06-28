"""Subprocess wrapper for intentframe-integrations CLI."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CliResult:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str


def resolve_cli_bin() -> str:
    override = os.environ.get("INTENTFRAME_INTEGRATIONS_BIN")
    if override:
        return override
    found = shutil.which("intentframe-integrations")
    if found:
        return found
    venv_candidate = Path(sys.executable).resolve().parent / "intentframe-integrations"
    if venv_candidate.is_file():
        return str(venv_candidate)
    raise RuntimeError(
        "intentframe-integrations not found on PATH. "
        "Install the CLI or set INTENTFRAME_INTEGRATIONS_BIN."
    )


def run_cli(args: list[str], *, timeout: float | None = 300.0) -> CliResult:
    bin_path = resolve_cli_bin()
    argv = [bin_path, *args]
    proc = subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=os.environ.copy(),
    )
    return CliResult(
        argv=argv,
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
