"""Install and verify Hermes ↔ IntentFrame integration (plugin + adapter)."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from intentframe_integrations.adapter_lifecycle import (
    adapter_log_file,
    adapter_status_line,
    adapter_venv_python,
    integration_state_dir,
    is_adapter_running,
    sync_adapter_venv,
)
from intentframe_integrations.hermes_install import install_status_lines, resolve_hermes_bin
from intentframe_integrations.hermes_paths import (
    hermes_config_path,
    hermes_home,
    hermes_plugins_dir,
)
from intentframe_integrations.integration_pack import IntegrationPack, load_integration_pack
from intentframe_integrations.paths import agent_config_path, repo_root

PLUGIN_KEY = "intentframe-terminal"
PLUGIN_DIR_NAME = "intentframe-terminal"


def plugin_source_dir() -> Path:
    return repo_root() / "integrations" / "hermes" / "plugin" / PLUGIN_DIR_NAME


def plugin_install_path() -> Path:
    return hermes_plugins_dir() / PLUGIN_DIR_NAME


@dataclass(frozen=True)
class IntegrateResult:
    plugin_installed: bool
    config_updated: bool
    adapter_venv_synced: bool
    messages: tuple[str, ...]


def _resolve_symlink_target(path: Path) -> Path | None:
    if not path.is_symlink():
        return None
    try:
        return path.resolve()
    except OSError:
        return None


def is_plugin_installed(*, source: Path | None = None) -> bool:
    dest = plugin_install_path()
    src = source or plugin_source_dir()
    if not dest.exists():
        return False
    if dest.is_symlink():
        target = _resolve_symlink_target(dest)
        return target == src.resolve()
    if dest.is_dir():
        return (dest / "plugin.yaml").is_file() and (dest / "__init__.py").is_file()
    return False


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return raw if isinstance(raw, dict) else {}


def _dump_yaml(data: dict[str, Any]) -> str:
    return yaml.safe_dump(data, default_flow_style=False, sort_keys=False)


def _backup_config(path: Path) -> None:
    if not path.is_file():
        return
    backup = path.with_name(f"{path.name}.intentframe.bak")
    shutil.copy2(path, backup)


def _try_append_plugin_enabled_in_place(text: str, plugin_key: str) -> str | None:
    cfg = yaml.safe_load(text)
    if not isinstance(cfg, dict):
        return None
    plugins = cfg.get("plugins")
    if not isinstance(plugins, dict):
        return None
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        return None
    if plugin_key in enabled:
        return None

    lines = text.splitlines(keepends=True)
    in_plugins = False
    in_enabled = False
    list_indent = ""
    insert_at: int | None = None

    for index, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("plugins:"):
            in_plugins = True
            in_enabled = False
            continue
        if not in_plugins:
            continue
        if stripped.startswith("enabled:"):
            in_enabled = True
            list_indent = line[: len(line) - len(stripped)] + "  "
            if stripped.strip() == "enabled: []":
                lines[index] = f"{line[: len(line) - len(stripped)]}enabled:\n"
                insert_at = index + 1
            continue
        if in_enabled:
            if stripped.startswith("- "):
                insert_at = index + 1
                continue
            if stripped and not stripped.startswith("#"):
                break

    if insert_at is None:
        return None

    lines.insert(insert_at, f"{list_indent}- {plugin_key}\n")
    return "".join(lines)


def is_plugin_enabled(config_path: Path | None = None) -> bool:
    cfg = _load_yaml(config_path or hermes_config_path())
    plugins = cfg.get("plugins")
    if not isinstance(plugins, dict):
        return False
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        return False
    return PLUGIN_KEY in enabled


def merge_plugin_enabled(config_path: Path | None = None) -> bool:
    """Ensure ``intentframe-terminal`` is in ``plugins.enabled``. Returns True if changed."""
    path = config_path or hermes_config_path()
    if is_plugin_enabled(path):
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(
            _dump_yaml({"plugins": {"enabled": [PLUGIN_KEY]}}),
            encoding="utf-8",
        )
        return True

    original = path.read_text(encoding="utf-8")
    updated = _try_append_plugin_enabled_in_place(original, PLUGIN_KEY)
    if updated is not None:
        _backup_config(path)
        path.write_text(updated, encoding="utf-8")
        return True

    cfg = _load_yaml(path)
    plugins = cfg.setdefault("plugins", {})
    if not isinstance(plugins, dict):
        plugins = {}
        cfg["plugins"] = plugins
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        enabled = []
        plugins["enabled"] = enabled
    enabled.append(PLUGIN_KEY)
    _backup_config(path)
    path.write_text(_dump_yaml(cfg), encoding="utf-8")
    return True


def install_plugin(*, copy: bool = False, source: Path | None = None) -> Path:
    """Install plugin to ~/.hermes/plugins/. Returns install path."""
    import shutil

    src = (source or plugin_source_dir()).resolve()
    if not (src / "plugin.yaml").is_file():
        raise FileNotFoundError(f"Plugin source not found: {src}")

    dest = plugin_install_path()
    hermes_plugins_dir().mkdir(parents=True, exist_ok=True)

    if dest.exists() or dest.is_symlink():
        if dest.is_symlink():
            dest.unlink()
        elif dest.is_dir():
            shutil.rmtree(dest)
        elif dest.is_file():
            dest.unlink()

    if copy:
        shutil.copytree(src, dest)
    else:
        dest.symlink_to(src)

    return dest


def format_env_exports(pack: IntegrationPack) -> str:
    lines = []
    for key, value in pack.agent.env.items():
        expanded = os.path.expanduser(value)
        if " " in expanded or "$" in expanded:
            lines.append(f'export {key}="{expanded}"')
        else:
            lines.append(f"export {key}={expanded}")
    return "\n".join(lines)


def integrate_hermes(
    pack: IntegrationPack,
    *,
    copy: bool = False,
    skip_config: bool = False,
    sync_adapter: bool = True,
) -> IntegrateResult:
    messages: list[str] = []
    src = plugin_source_dir()

    if not src.is_dir():
        raise FileNotFoundError(f"Hermes plugin source missing: {src}")

    was_installed = is_plugin_installed(source=src)
    dest = install_plugin(copy=copy, source=src)
    if was_installed:
        messages.append(f"Plugin already installed at {dest}")
    else:
        mode = "copied" if copy else "symlinked"
        messages.append(f"Plugin {mode} to {dest}")

    config_updated = False
    if not skip_config:
        config_updated = merge_plugin_enabled()
        if config_updated:
            messages.append(f"Added {PLUGIN_KEY!r} to {hermes_config_path()}")
        elif is_plugin_enabled():
            messages.append(f"Plugin already enabled in {hermes_config_path()}")
        else:
            messages.append(
                f"No Hermes config at {hermes_config_path()} — create one with plugins.enabled"
            )

    adapter_synced = False
    if sync_adapter and pack.adapter is not None:
        sync_adapter_venv(pack)
        adapter_synced = True
        messages.append(
            f"Adapter venv synced at {integration_state_dir(pack.agent.agent_id) / '.venv'}"
        )

    return IntegrateResult(
        plugin_installed=True,
        config_updated=config_updated,
        adapter_venv_synced=adapter_synced,
        messages=tuple(messages),
    )


@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    lines: tuple[str, ...]


def doctor_hermes(
    pack: IntegrationPack,
    *,
    require_hermes: bool = True,
    require_integration: bool = True,
) -> DoctorReport:
    lines: list[str] = []
    ok = True

    lines.extend(install_status_lines())
    lines.append(f"Agent config: {pack.agent.source_path}")
    lines.append(f"  agent_id: {pack.agent.agent_id}")
    lines.append(f"  user_id:  {pack.agent.user_id}")

    if os.environ.get("OPENAI_API_KEY"):
        lines.append("  OPENAI_API_KEY: set")
    elif require_integration:
        lines.append("  OPENAI_API_KEY: MISSING (required for IntentFrame runtime)")
        ok = False
    else:
        lines.append("  OPENAI_API_KEY: not set")

    from if_security_backend.runtime.paths import bridge_socket_path

    bridge_socket = bridge_socket_path()
    if bridge_socket.exists():
        lines.append(f"  backend bridge: present ({bridge_socket})")
    elif require_integration:
        lines.append(f"  backend bridge: not found — run: intentframe-integrations start hermes")
        ok = False
    else:
        lines.append(f"  backend bridge: not running ({bridge_socket})")

    src = plugin_source_dir()
    if src.is_dir():
        lines.append(f"  plugin source: {src}")
    else:
        lines.append(f"  plugin source: MISSING ({src})")
        ok = False

    dest = plugin_install_path()
    if is_plugin_installed(source=src):
        lines.append(f"  plugin install: ok ({dest})")
    elif require_integration:
        lines.append(f"  plugin install: missing — run: intentframe-integrations integrate hermes")
        ok = False
    else:
        lines.append(f"  plugin install: not installed ({dest})")

    hcfg = hermes_config_path()
    if is_plugin_enabled(hcfg):
        lines.append(f"  hermes config: {PLUGIN_KEY} enabled in {hcfg}")
    elif require_integration:
        if hcfg.is_file():
            lines.append(f"  hermes config: {PLUGIN_KEY} not in plugins.enabled ({hcfg})")
        else:
            lines.append(f"  hermes config: not found ({hcfg})")
        ok = False
    elif hcfg.is_file():
        lines.append(f"  hermes config: present ({hcfg}), plugin not enabled")
    else:
        lines.append(f"  hermes config: not found ({hcfg})")

    if pack.adapter is not None and require_integration:
        lines.append(f"  {adapter_status_line(pack)}")
        if not is_adapter_running(pack.agent.agent_id):
            ok = False
        venv_py = adapter_venv_python(pack.agent.agent_id)
        if venv_py.is_file():
            lines.append(f"  adapter venv: {venv_py.parent.parent}")
        else:
            lines.append("  adapter venv: not synced — run: intentframe-integrations integrate hermes")
            ok = False
        log = adapter_log_file(pack.agent.agent_id)
        if log.is_file():
            lines.append(f"  adapter log: {log}")

    if require_integration:
        adapter_socket = pack.agent.env.get("IF_AGENT_ADAPTER_SOCKET")
        if adapter_socket:
            expanded = Path(os.path.expanduser(adapter_socket))
            if os.environ.get("IF_AGENT_ADAPTER_SOCKET"):
                lines.append("  env IF_AGENT_ADAPTER_SOCKET: set")
            else:
                lines.append("  env IF_AGENT_ADAPTER_SOCKET: not set (required by Hermes plugin)")
                ok = False
            if not expanded.exists() and not is_adapter_running(pack.agent.agent_id):
                lines.append(f"  adapter socket: not found ({expanded})")
        else:
            lines.append("  env IF_AGENT_ADAPTER_SOCKET: missing from agent.json")
            ok = False
    elif pack.adapter is not None:
        lines.append(f"  {adapter_status_line(pack)}")

    if require_hermes and resolve_hermes_bin() is None:
        ok = False

    return DoctorReport(ok=ok, lines=tuple(lines))


def load_hermes_pack() -> IntegrationPack:
    return load_integration_pack(agent_config_path("hermes"))
