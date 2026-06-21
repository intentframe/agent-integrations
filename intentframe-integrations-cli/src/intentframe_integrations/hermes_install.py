"""Install and resolve Hermes Agent for IntentFrame integrations."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from intentframe_integrations.hermes_paths import hermes_home
from intentframe_integrations.adapter_lifecycle import integration_state_dir

DEFAULT_HERMES_AGENT_VERSION = "0.17.0"
HERMES_AGENT_PYTHON = "3.12"
INSTALL_RECORD_NAME = "hermes-install.json"
HERMES_VENV_DIR_NAME = "hermes-agent-venv"


class HermesInstallError(Exception):
    pass


@dataclass(frozen=True)
class InstallResult:
    installed: bool
    already_installed: bool
    binary: Path
    version: str
    messages: tuple[str, ...]


def _version_override() -> str:
    return os.environ.get("INTENTFRAME_HERMES_AGENT_VERSION", DEFAULT_HERMES_AGENT_VERSION)


def managed_venv_dir() -> Path:
    return integration_state_dir("hermes") / HERMES_VENV_DIR_NAME


def install_record_path() -> Path:
    return integration_state_dir("hermes") / INSTALL_RECORD_NAME


def managed_hermes_bin() -> Path:
    return managed_venv_dir() / "bin" / "hermes"


def _load_install_record() -> dict[str, object] | None:
    path = install_record_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return raw if isinstance(raw, dict) else None


def _write_install_record(*, version: str, binary: Path, venv: Path) -> None:
    record = {
        "version": version,
        "python": HERMES_AGENT_PYTHON,
        "venv": str(venv),
        "binary": str(binary),
        "installed_at": datetime.now(UTC).isoformat(),
    }
    path = install_record_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")


def is_managed_hermes_installed(*, version: str | None = None) -> bool:
    binary = managed_hermes_bin()
    if not binary.is_file():
        return False
    record = _load_install_record()
    if record is None:
        return False
    if version is not None and record.get("version") != version:
        return False
    return _verify_hermes_binary(binary)


def _verify_hermes_binary(binary: Path) -> bool:
    if not binary.is_file():
        return False
    try:
        proc = subprocess.run(
            [str(binary), "--version"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def resolve_hermes_bin() -> Path | None:
    """Resolve Hermes CLI: HERMES_BIN → managed install → PATH."""
    override = os.environ.get("HERMES_BIN")
    if override:
        path = Path(os.path.expanduser(override))
        if path.is_file() and _verify_hermes_binary(path):
            return path

    managed = managed_hermes_bin()
    if managed.is_file() and _verify_hermes_binary(managed):
        return managed

    discovered = shutil.which("hermes")
    if discovered:
        path = Path(discovered)
        if _verify_hermes_binary(path):
            return path
    return None


def bootstrap_hermes_home() -> Path:
    """Ensure Hermes data directory exists under HERMES_HOME."""
    home = hermes_home()
    home.mkdir(parents=True, exist_ok=True)
    (home / "plugins").mkdir(parents=True, exist_ok=True)
    return home


def install_hermes_agent(*, version: str | None = None, force: bool = False) -> InstallResult:
    """Install Hermes Agent into the orchestrator-managed venv."""
    target_version = version or _version_override()
    messages: list[str] = []
    binary = managed_hermes_bin()
    venv_dir = managed_venv_dir()

    if not force and is_managed_hermes_installed(version=target_version):
        messages.append(f"Hermes Agent {target_version} already installed at {binary}")
        return InstallResult(
            installed=True,
            already_installed=True,
            binary=binary,
            version=target_version,
            messages=tuple(messages),
        )

    integration_state_dir("hermes").mkdir(parents=True, exist_ok=True)
    bootstrap_hermes_home()

    if not (venv_dir / "bin" / "python").is_file() or force:
        if venv_dir.exists() and force:
            shutil.rmtree(venv_dir)
        subprocess.check_call(
            [
                "uv",
                "venv",
                str(venv_dir),
                "--python",
                HERMES_AGENT_PYTHON,
                "--no-project",
            ],
        )
        messages.append(f"Created Hermes venv at {venv_dir} (Python {HERMES_AGENT_PYTHON})")
    else:
        messages.append(f"Using existing Hermes venv at {venv_dir}")

    subprocess.check_call(
        [
            "uv",
            "pip",
            "install",
            "--python",
            str(venv_dir / "bin" / "python"),
            f"hermes-agent=={target_version}",
            "-q",
        ],
    )
    messages.append(f"Installed hermes-agent=={target_version}")

    if not binary.is_file():
        raise HermesInstallError(f"Hermes binary missing after install: {binary}")

    if not _verify_hermes_binary(binary):
        raise HermesInstallError(f"Hermes binary failed verification: {binary}")

    _write_install_record(version=target_version, binary=binary, venv=venv_dir)
    messages.append(f"Hermes CLI ready at {binary}")
    messages.append(f"Hermes home: {hermes_home()}")

    return InstallResult(
        installed=True,
        already_installed=False,
        binary=binary,
        version=target_version,
        messages=tuple(messages),
    )


def install_status_lines() -> tuple[str, ...]:
    lines = [
        f"  HOME: {Path.home()}",
        f"  HERMES_HOME: {hermes_home()}",
    ]
    resolved = resolve_hermes_bin()
    if resolved:
        lines.append(f"  hermes CLI: {resolved}")
        if resolved == managed_hermes_bin():
            record = _load_install_record()
            if record and isinstance(record.get("version"), str):
                lines.append(f"  hermes install: managed ({record['version']})")
            else:
                lines.append("  hermes install: managed")
        else:
            lines.append("  hermes install: external (PATH or HERMES_BIN)")
    else:
        lines.append("  hermes CLI: not found — run: intentframe-integrations install hermes")
    return tuple(lines)
