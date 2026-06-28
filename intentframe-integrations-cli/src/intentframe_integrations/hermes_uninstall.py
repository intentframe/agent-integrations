"""Remove IntentFrame Hermes integration from a machine."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from intentframe_integrations.adapter_lifecycle import integration_state_dir
from intentframe_integrations.hermes_integrate import (
    PLUGIN_KEY,
    _backup_config,
    _dump_yaml,
    _load_yaml,
    plugin_install_path,
)
from intentframe_integrations.hermes_paths import hermes_home
from intentframe_integrations.integration_pack import IntegrationPack

CLI_NAMES = ("intentframe-integrations",)
HERMES_CLI_NAMES = ("hermes",)
INSTALLER_RC_MARKER = "# Added by IntentFrame Hermes installer"
INSTALLER_PATH_LINE = 'export PATH="$HOME/.local/bin:$PATH"'


@dataclass(frozen=True)
class UninstallResult:
    messages: tuple[str, ...]


def remove_plugin_enabled(config_path: Path | None = None) -> bool:
    """Remove ``intentframe-gate`` from ``plugins.enabled``. Returns True if changed."""
    path = config_path or hermes_home() / "config.yaml"
    if not path.is_file():
        return False
    cfg = _load_yaml(path)
    plugins = cfg.get("plugins")
    if not isinstance(plugins, dict):
        return False
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list) or PLUGIN_KEY not in enabled:
        return False
    _backup_config(path)
    plugins["enabled"] = [item for item in enabled if item != PLUGIN_KEY]
    path.write_text(_dump_yaml(cfg), encoding="utf-8")
    return True


def strip_env_keys(env_path: Path, keys: frozenset[str]) -> bool:
    if not env_path.is_file():
        return False
    kept: list[str] = []
    changed = False
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in keys:
                changed = True
                continue
        kept.append(line)
    if not changed:
        return False
    text = "\n".join(kept).rstrip()
    env_path.write_text(f"{text}\n" if text else "", encoding="utf-8")
    return True


def remove_installer_shell_path() -> list[str]:
    """Remove PATH block appended by install-hermes-plugin.sh. Returns changed rc paths."""
    changed: list[str] = []
    home = Path.home()
    for rc in (home / ".zshrc", home / ".bashrc", home / ".profile"):
        if not rc.is_file():
            continue
        lines = rc.read_text(encoding="utf-8").splitlines(keepends=True)
        out: list[str] = []
        index = 0
        file_changed = False
        while index < len(lines):
            line = lines[index]
            if INSTALLER_RC_MARKER in line:
                file_changed = True
                if out and out[-1].strip() == "":
                    out.pop()
                index += 1
                if index < len(lines) and INSTALLER_PATH_LINE in lines[index]:
                    index += 1
                if index < len(lines) and lines[index].strip() == "":
                    index += 1
                continue
            out.append(line)
            index += 1
        if file_changed:
            text = "".join(out).rstrip()
            rc.write_text(f"{text}\n" if text else "", encoding="utf-8")
            changed.append(str(rc))
    return changed


def _remove_path(path: Path, messages: list[str], label: str) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)
    messages.append(f"Removed {label}: {path}")


def _remove_bin_symlinks(names: tuple[str, ...], messages: list[str], label: str) -> None:
    for name in names:
        for parent in (Path.home() / ".local" / "bin", Path("/usr/local/bin")):
            target = parent / name
            if target.exists() or target.is_symlink():
                _remove_path(target, messages, label)


def _remove_hermes_config_backups(messages: list[str]) -> None:
    home = hermes_home()
    if not home.is_dir():
        return
    for backup in home.glob("*.intentframe.bak"):
        _remove_path(backup, messages, "Hermes config backup")


def uninstall_hermes(
    pack: IntegrationPack,
    *,
    remove_hermes: bool = False,
) -> UninstallResult:
    messages: list[str] = []
    env_keys = frozenset(pack.agent.env)

    try:
        from intentframe_control_plane.lifecycle import stop_control_plane

        stop_control_plane(quiet=True)
        messages.append("Stopped IntentFrame control plane")
    except Exception:
        pass

    plugin_dest = plugin_install_path()
    if plugin_dest.exists() or plugin_dest.is_symlink():
        _remove_path(plugin_dest, messages, "Hermes plugin")
    else:
        messages.append(f"Hermes plugin not present: {plugin_dest}")

    if remove_plugin_enabled():
        messages.append(f"Disabled {PLUGIN_KEY!r} in {hermes_home() / 'config.yaml'}")

    env_path = hermes_home() / ".env"
    if strip_env_keys(env_path, env_keys):
        messages.append(f"Removed IntentFrame env keys from {env_path}")

    _remove_hermes_config_backups(messages)

    integration_dir = integration_state_dir(pack.agent.agent_id)
    if integration_dir.exists():
        _remove_path(integration_dir, messages, "IntentFrame integration state")

    intentframe_home = Path.home() / ".intentframe"
    if intentframe_home.exists():
        _remove_path(intentframe_home, messages, "IntentFrame home")

    _remove_bin_symlinks(CLI_NAMES, messages, "CLI symlink")

    for rc_path in remove_installer_shell_path():
        messages.append(f"Removed installer PATH block from {rc_path}")

    if remove_hermes:
        _remove_path(hermes_home(), messages, "Hermes home")
        _remove_bin_symlinks(HERMES_CLI_NAMES, messages, "Hermes CLI symlink")

    return UninstallResult(messages=tuple(messages))
