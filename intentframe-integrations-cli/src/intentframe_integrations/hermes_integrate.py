"""Install and verify Hermes ↔ IntentFrame integration (plugin + adapter).

``integrate hermes`` copies committed governance templates to runtime (first use only);
it never regenerates manifest or policy from ``tools.yaml``. Dev artifact parity is
enforced by ``tests/intentframe_integrations/test_actions_manifest.py``.
"""

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
from intentframe_integrations.hermes_governance_contract import (
    actions_manifest_runtime_path,
    catalog_generic_action_ids,
    default_governance_template_path,
    ensure_runtime_actions_manifest,
    ensure_runtime_governance_yaml,
    governance_yaml_runtime_path,
    reset_runtime_governance_yaml,
)
from intentframe_integrations.policy_contract import (
    ensure_runtime_policy_yaml,
    policy_yaml_runtime_path,
    reset_runtime_policy_yaml,
    shipped_policy_template_path,
)
from intentframe_integrations.integration_pack import IntegrationPack, load_integration_pack
from intentframe_integrations.paths import agent_config_path, repo_root

PLUGIN_KEY = "intentframe-gate"
PLUGIN_DIR_NAME = "intentframe-gate"
REMOVED_PLUGIN_KEYS = frozenset({"intentframe-terminal"})


def plugin_source_dir() -> Path:
    return repo_root() / "integrations" / "hermes" / "plugin" / PLUGIN_DIR_NAME


def executor_profile_path() -> Path:
    return (
        repo_root()
        / "if-integration-backend"
        / "src"
        / "if_security_backend"
        / "config"
        / "profiles"
        / "executor.yaml"
    )


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


def _sanitize_plugin_enabled(cfg: dict[str, Any]) -> bool:
    plugins = cfg.get("plugins")
    if not isinstance(plugins, dict):
        return False
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        return False

    changed = False
    cleaned: list[str] = []
    for item in enabled:
        if not isinstance(item, str):
            changed = True
            continue
        if item in REMOVED_PLUGIN_KEYS:
            changed = True
            continue
        if item not in cleaned:
            cleaned.append(item)
        else:
            changed = True
    if cleaned != enabled:
        plugins["enabled"] = cleaned
        changed = True
    return changed


def merge_plugin_enabled(config_path: Path | None = None) -> bool:
    """Ensure ``intentframe-gate`` is in ``plugins.enabled``. Returns True if changed."""
    path = config_path or hermes_config_path()
    changed = False
    if path.is_file():
        cfg = _load_yaml(path)
        if _sanitize_plugin_enabled(cfg):
            _backup_config(path)
            path.write_text(_dump_yaml(cfg), encoding="utf-8")
            changed = True

    if is_plugin_enabled(path):
        return changed

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
    for key, default in pack.agent.env.items():
        raw = os.environ.get(key, default)
        expanded = os.path.expanduser(raw)
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
    reset_governance: bool = False,
    reset_policy: bool = False,
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

    if reset_governance:
        gov_dest = reset_runtime_governance_yaml(pack.agent.agent_id)
        messages.append(f"Governance config reset from default template to {gov_dest}")
    else:
        gov_dest = ensure_runtime_governance_yaml(pack.agent.agent_id)
        messages.append(f"Governance config at {gov_dest}")

    if reset_policy:
        pol_dest = reset_runtime_policy_yaml(pack)
        messages.append(f"Policy config reset from shipped default to {pol_dest}")
    else:
        pol_dest = ensure_runtime_policy_yaml(pack)
        messages.append(f"Policy config at {pol_dest}")

    manifest_dest = ensure_runtime_actions_manifest(pack.agent.agent_id)
    messages.append(f"Actions manifest at {manifest_dest}")

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


def _load_governance_contract() -> dict[str, dict[str, str | list[str]]]:
    path = default_governance_template_path()
    if not path.is_file():
        raise FileNotFoundError(f"Governance contract missing: {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tools = raw.get("tools")
    if not isinstance(tools, dict) or not tools:
        raise ValueError(f"Governance contract has no tools: {path}")
    out: dict[str, dict[str, str | list[str]]] = {}
    for name, spec in tools.items():
        if not isinstance(name, str) or not isinstance(spec, dict):
            continue
        action = spec.get("action")
        mapper = spec.get("mapper")
        actions = spec.get("actions")
        if not isinstance(action, str) or not isinstance(mapper, str):
            continue
        entry: dict[str, str | list[str]] = {"action": action, "mapper": mapper}
        if isinstance(actions, list):
            entry["actions"] = [str(item) for item in actions]
        out[name] = entry
    return out


def governance_doctor_lines(pack: IntegrationPack) -> tuple[list[str], bool]:
    lines: list[str] = []
    ok = True
    try:
        contract = _load_governance_contract()
    except (OSError, ValueError) as exc:
        return [f"  governance: ERROR — {exc}"], False

    governed_actions: set[str] = set()
    for spec in contract.values():
        governed_actions.add(str(spec["action"]))
        extra = spec.get("actions")
        if isinstance(extra, list):
            governed_actions.update(str(action) for action in extra)
    agent_actions = set(pack.agent.action_types)
    missing_agent = sorted(governed_actions - agent_actions)
    if missing_agent:
        ok = False
        lines.append(
            f"  governance: action_types missing from agent.json: {missing_agent}"
        )
    else:
        lines.append(
            f"  governance: {len(contract)} governed tools; "
            f"agent.json covers {len(governed_actions)} action(s)"
        )

    policy_path = policy_yaml_runtime_path(pack.agent.agent_id)
    if not policy_path.is_file():
        try:
            policy_path = ensure_runtime_policy_yaml(pack)
        except FileNotFoundError:
            policy_path = shipped_policy_template_path(pack)

    if policy_path.is_file():
        policy_raw = yaml.safe_load(policy_path.read_text(encoding="utf-8")) or {}
        allowed = policy_raw.get("allowed_actions")
        if isinstance(allowed, dict):
            missing_policy = sorted(
                action for action in governed_actions if action not in allowed
            )
            if missing_policy:
                ok = False
                lines.append(
                    f"  policy: missing allowed_actions for governed tools: {missing_policy}"
                )
            else:
                lines.append(
                    f"  policy: runtime config at {policy_path} covers governed actions"
                )
        else:
            ok = False
            lines.append(f"  policy: {policy_path} has no allowed_actions mapping")
    else:
        ok = False
        lines.append("  policy: runtime policy file missing")

    tool_names = ", ".join(sorted(contract))
    lines.append(f"  governance tools: {tool_names}")

    catalog_generic = catalog_generic_action_ids()
    manifest_path = actions_manifest_runtime_path(pack.agent.agent_id)
    manifest_env_key = "IF_DYNAMIC_BUNDLE_MANIFEST"
    if catalog_generic:
        env_value = pack.agent.env.get(manifest_env_key, "").strip()
        if not env_value:
            ok = False
            lines.append(f"  manifest: {manifest_env_key} not set in agent.json")
        else:
            env_path = Path(os.path.expanduser(env_value))
            if env_path != manifest_path:
                ok = False
                lines.append(
                    f"  manifest: {manifest_env_key}={env_value!r} does not match "
                    f"expected {manifest_path}"
                )
            elif not manifest_path.is_file():
                ok = False
                lines.append(
                    f"  manifest: missing at {manifest_path} "
                    f"(run: intentframe-integrations integrate hermes)"
                )
            else:
                present = {
                    part.strip()
                    for part in manifest_path.read_text(encoding="utf-8").split(",")
                    if part.strip()
                }
                missing = sorted(catalog_generic - present)
                if missing:
                    ok = False
                    lines.append(
                        f"  manifest: missing catalog action(s) {missing} at {manifest_path}"
                    )
                else:
                    lines.append(
                        f"  manifest: ok at {manifest_path} "
                        f"({manifest_env_key} configured)"
                    )
    else:
        lines.append("  manifest: no generic mapper tools in catalog")

    executor_path = executor_profile_path()
    if executor_path.is_file():
        executor_raw = yaml.safe_load(executor_path.read_text(encoding="utf-8")) or {}
        supported = (
            executor_raw.get("pack_options", {})
            .get("validate_only", {})
            .get("supported_actions")
        )
        if isinstance(supported, list):
            missing_executor = sorted(governed_actions - {str(item) for item in supported})
            if missing_executor:
                ok = False
                lines.append(
                    f"  executor: missing supported_actions: {missing_executor}"
                )
            else:
                lines.append("  executor: supported_actions covers governed actions")
        else:
            ok = False
            lines.append(f"  executor: {executor_path} missing validate_only.supported_actions")
    else:
        ok = False
        lines.append(f"  executor: profile missing at {executor_path}")

    return lines, ok


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
    cfg = _load_yaml(hcfg) if hcfg.is_file() else {}
    plugins = cfg.get("plugins") if isinstance(cfg, dict) else None
    enabled = plugins.get("enabled") if isinstance(plugins, dict) else None
    has_gate = isinstance(enabled, list) and PLUGIN_KEY in enabled
    if has_gate:
        lines.append(f"  hermes config: {PLUGIN_KEY} enabled in {hcfg}")
    elif is_plugin_enabled(hcfg):
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

    gov_lines, gov_ok = governance_doctor_lines(pack)
    lines.extend(gov_lines)
    if not gov_ok and require_integration:
        ok = False

    return DoctorReport(ok=ok, lines=tuple(lines))


def load_hermes_pack() -> IntegrationPack:
    """Parse Hermes agent.json only — no env side effects.

    CLI commands use ``integration_pack.load_and_activate_pack("hermes")`` instead.
    """
    return load_integration_pack(agent_config_path("hermes"))
