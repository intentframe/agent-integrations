"""Isolated HOME/HERMES_HOME for Hermes gateway E2E tests."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

# macOS AF_UNIX path limit is 104 bytes (including NUL).
_MAX_UDS_PATH_LEN = 104
_LONGEST_UDS_NAME = "policy-registry.sock"

# Test-only Hermes LLM defaults (production CLI never writes these).
HERMES_E2E_OPENAI_PROVIDER = "openai-api"
# gpt-4o-mini is chat-completions-only; Hermes 0.17 auto-picks codex_responses for
# api.openai.com unless api_mode is set explicitly.
HERMES_E2E_OPENAI_API_MODE = "chat_completions"
HERMES_E2E_DEFAULT_MODEL = "gpt-4o-mini"
HERMES_E2E_MODEL_ENV = "INTENTFRAME_HERMES_E2E_MODEL"


@dataclass
class IsolatedEnv:
    test_root: Path
    home: Path
    hermes_home: Path
    api_port: int
    api_key: str
    run_id: str
    real_hermes_path: Path
    real_if_hermes_path: Path
    _saved_env: dict[str, str | None] = field(default_factory=dict)
    _real_hermes_snapshot: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    _real_if_hermes_snapshot: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    tracked_pids: list[int] = field(default_factory=list)
    _active: bool = False

    @property
    def integration_state(self) -> Path:
        return self.home / ".intentframe" / "integrations" / "hermes"

    @property
    def managed_hermes_bin(self) -> Path:
        exe = "hermes.exe" if os.name == "nt" else "hermes"
        scripts = "Scripts" if os.name == "nt" else "bin"
        return self.integration_state / "hermes-agent-venv" / scripts / exe

    @property
    def plugin_install_path(self) -> Path:
        return self.hermes_home / "plugins" / "intentframe-gate"

    @property
    def hermes_config_path(self) -> Path:
        return self.hermes_home / "config.yaml"

    @property
    def gateway_log(self) -> Path:
        return self.integration_state / "gateway.log"

    @property
    def adapter_log(self) -> Path:
        return self.integration_state / "adapter.log"

    @property
    def bridge_log(self) -> Path:
        return self.home / ".intentframe" / "backend" / "bridge.log"

    @property
    def supervisor_log(self) -> Path:
        return self.home / ".intentframe" / "backend" / "supervisor.log"

    @property
    def executor_log(self) -> Path:
        return self.home / ".intentframe" / "logs" / "executor.log"

    @property
    def intentframe_server_log(self) -> Path:
        return self.home / ".intentframe" / "logs" / "intentframe-server.log"

    @property
    def hermes_env_file(self) -> Path:
        return self.hermes_home / ".env"

    def sandbox_log_catalog(self) -> tuple[tuple[str, Path], ...]:
        """Labelled sandbox log paths for tailing during E2E (not real ~/.intentframe)."""
        return (
            ("Hermes gateway", self.gateway_log),
            ("Hermes adapter", self.adapter_log),
            ("IntentFrame bridge", self.bridge_log),
            ("IntentFrame supervisor", self.supervisor_log),
            ("IntentFrame executor", self.executor_log),
            ("IntentFrame core (policy/AE)", self.intentframe_server_log),
            ("Hermes config", self.hermes_config_path),
            ("Hermes .env", self.hermes_env_file),
        )


def format_sandbox_log_paths(env: IsolatedEnv) -> str:
    lines = [
        f"Sandbox HOME={env.home}",
        f"Sandbox HERMES_HOME={env.hermes_home}",
        "Tail during this run (not ~/.intentframe):",
    ]
    for label, path in env.sandbox_log_catalog():
        lines.append(f"  {label}: {path}")
    return "\n".join(lines)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _short_test_root() -> Path:
    """Create a temp dir with a short path so AF_UNIX sockets fit macOS limits."""
    run_id = uuid.uuid4().hex[:8]
    if os.name == "nt":
        base = Path(tempfile.gettempdir())
    else:
        base = Path("/tmp")
    root = base / f"hg{run_id}"
    root.mkdir(mode=0o700, exist_ok=False)
    return root


def _longest_uds_path(home: Path) -> Path:
    return home / ".intentframe" / "run" / _LONGEST_UDS_NAME


def sandbox_backend_uds_paths(home: Path) -> tuple[Path, ...]:
    """Unix socket paths used when HOME is the E2E sandbox."""
    run = home / ".intentframe" / "run"
    backend = home / ".intentframe" / "backend"
    return (
        run / "policy-registry.sock",
        run / "resource-registry.sock",
        run / "executor.sock",
        run / "intentframe.sock",
        backend / "bridge.sock",
    )


def _assert_uds_paths_fit(home: Path) -> None:
    if os.name == "nt":
        return
    for path in sandbox_backend_uds_paths(home):
        resolved = str(path)
        if len(resolved) >= _MAX_UDS_PATH_LEN:
            raise RuntimeError(
                f"E2E sandbox UDS path too long ({len(resolved)} >= {_MAX_UDS_PATH_LEN}): {resolved}"
            )


def _read_pid(path: Path) -> int | None:
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _snapshot_dir(path: Path) -> tuple[tuple[str, int], ...]:
    if not path.exists():
        return ()
    entries: list[tuple[str, int]] = []
    for item in path.rglob("*"):
        if item.is_file():
            try:
                rel = str(item.relative_to(path))
                entries.append((rel, item.stat().st_mtime_ns))
            except OSError:
                continue
    return tuple(sorted(entries))


def _copy_or_link_tool(tool: str, target_dir: Path) -> None:
    resolved = shutil.which(tool)
    if not resolved:
        raise RuntimeError(f"Required tool {tool!r} not found on PATH")
    src = Path(resolved)
    dest = target_dir / src.name
    if dest.exists():
        return
    try:
        dest.symlink_to(src)
    except OSError:
        shutil.copy2(src, dest)


def _safe_path(test_root: Path) -> str:
    shim_dir = test_root / "bin"
    shim_dir.mkdir(exist_ok=True)
    _copy_or_link_tool("uv", shim_dir)

    original_parts = [part for part in os.environ.get("PATH", "").split(os.pathsep) if part]
    safe_parts = [str(shim_dir)]
    for part in original_parts:
        if shutil.which("hermes", path=part):
            continue
        if part not in safe_parts:
            safe_parts.append(part)
    return os.pathsep.join(safe_parts)


def create_isolated_env(*, api_port: int | None = None, api_key: str | None = None) -> IsolatedEnv:
    test_root = _short_test_root()
    home = test_root
    hermes_home = test_root / "hh"
    hermes_home.mkdir()
    _assert_uds_paths_fit(home)
    run_id = uuid.uuid4().hex[:12]
    key = api_key or f"intentframe-hermes-e2e-{run_id}"
    real_hermes = Path.home() / ".hermes"
    real_if_hermes = Path.home() / ".intentframe" / "integrations" / "hermes"
    return IsolatedEnv(
        test_root=test_root,
        home=home,
        hermes_home=hermes_home,
        api_port=api_port or _free_port(),
        api_key=key,
        run_id=run_id,
        real_hermes_path=real_hermes,
        real_if_hermes_path=real_if_hermes,
        _real_hermes_snapshot=_snapshot_dir(real_hermes),
        _real_if_hermes_snapshot=_snapshot_dir(real_if_hermes),
    )


def activate(env: IsolatedEnv) -> None:
    if env._active:
        return
    keys = (
        "HOME",
        "HERMES_HOME",
        "INTENTFRAME_HERMES_API_KEY",
        "API_SERVER_PORT",
        "API_SERVER_KEY",
        "PATH",
        "HERMES_BIN",
    )
    env._saved_env = {key: os.environ.get(key) for key in keys}
    os.environ["HOME"] = str(env.home)
    os.environ["HERMES_HOME"] = str(env.hermes_home)
    os.environ["INTENTFRAME_HERMES_API_KEY"] = env.api_key
    os.environ["API_SERVER_PORT"] = str(env.api_port)
    os.environ["API_SERVER_KEY"] = env.api_key
    os.environ["PATH"] = _safe_path(env.test_root)
    os.environ.pop("HERMES_BIN", None)
    env._active = True


def _e2e_openai_model() -> str:
    return os.environ.get(HERMES_E2E_MODEL_ENV, HERMES_E2E_DEFAULT_MODEL)


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _write_env_file(path: Path, updates: dict[str, str]) -> None:
    existing = _parse_env_file(path)
    existing.update(updates)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{key}={value}" for key, value in existing.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def seed_hermes_openai_for_e2e(env: IsolatedEnv) -> None:
    """Seed isolated HERMES_HOME with OpenAI provider config for gateway E2E only."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required to seed Hermes OpenAI config for gateway E2E"
        )

    model = _e2e_openai_model()
    env.hermes_home.mkdir(parents=True, exist_ok=True)

    config_path = env.hermes_config_path
    cfg: dict[str, object] = {}
    if config_path.is_file():
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            cfg = raw

    model_cfg = cfg.get("model")
    if not isinstance(model_cfg, dict):
        model_cfg = {}
        cfg["model"] = model_cfg
    model_cfg["provider"] = HERMES_E2E_OPENAI_PROVIDER
    model_cfg["default"] = model
    model_cfg["api_mode"] = HERMES_E2E_OPENAI_API_MODE

    plugins = cfg.get("plugins")
    if not isinstance(plugins, dict):
        plugins = {}
        cfg["plugins"] = plugins
    enabled = plugins.get("enabled")
    if not isinstance(enabled, list):
        plugins["enabled"] = []

    config_path.write_text(yaml.safe_dump(cfg, default_flow_style=False, sort_keys=False), encoding="utf-8")
    _write_env_file(env.hermes_env_file, {"OPENAI_API_KEY": api_key})


def assert_hermes_openai_seeded(env: IsolatedEnv) -> None:
    """Verify test sandbox Hermes config points at OpenAI (not real ~/.hermes)."""
    if not env.hermes_config_path.is_file():
        raise AssertionError(f"Missing Hermes config: {env.hermes_config_path}")

    raw = yaml.safe_load(env.hermes_config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AssertionError(f"Invalid Hermes config: {env.hermes_config_path}")

    model = raw.get("model")
    if not isinstance(model, dict):
        raise AssertionError("Hermes config missing model section")

    provider = model.get("provider")
    if provider != HERMES_E2E_OPENAI_PROVIDER:
        raise AssertionError(
            f"Expected Hermes provider {HERMES_E2E_OPENAI_PROVIDER!r}, got {provider!r}"
        )

    default = model.get("default")
    if not default:
        raise AssertionError("Hermes config missing model.default")

    api_mode = model.get("api_mode")
    if api_mode != HERMES_E2E_OPENAI_API_MODE:
        raise AssertionError(
            f"Expected Hermes api_mode {HERMES_E2E_OPENAI_API_MODE!r}, got {api_mode!r}"
        )

    env_values = _parse_env_file(env.hermes_env_file)
    if not env_values.get("OPENAI_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        raise AssertionError("OPENAI_API_KEY missing from sandbox .env and process env")


def deactivate(env: IsolatedEnv) -> None:
    if not env._active:
        return
    for key, value in env._saved_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    env._active = False


def expose_external_hermes_bin(env: IsolatedEnv) -> Path:
    """Simulate a user-installed Hermes binary exposed via HERMES_BIN."""
    if not env.managed_hermes_bin.is_file():
        raise AssertionError(f"Managed Hermes binary missing: {env.managed_hermes_bin}")

    scripts = "Scripts" if os.name == "nt" else "bin"
    exe = "hermes.exe" if os.name == "nt" else "hermes"
    external_dir = env.test_root / "external-hermes" / scripts
    external_dir.mkdir(parents=True, exist_ok=True)
    external_bin = external_dir / exe
    if external_bin.exists() or external_bin.is_symlink():
        external_bin.unlink()

    try:
        external_bin.symlink_to(env.managed_hermes_bin)
    except OSError:
        shutil.copy2(env.managed_hermes_bin, external_bin)
        if os.name != "nt":
            external_bin.chmod(0o755)

    os.environ["HERMES_BIN"] = str(external_bin)
    return external_bin


def record_runtime_pids(env: IsolatedEnv) -> None:
    """Track PIDs from orchestrator pid files for post-cleanup verification."""
    pid_files = [
        env.integration_state / "gateway.pid",
        env.integration_state / "adapter.pid",
        env.home / ".intentframe" / "backend" / "bridge.pid",
        env.home / ".intentframe" / "backend" / "supervisor.pid",
        env.home / ".intentframe" / "run" / "supervisor.pid",
    ]
    seen = set(env.tracked_pids)
    for path in pid_files:
        pid = _read_pid(path)
        if pid is None or pid in seen:
            continue
        env.tracked_pids.append(pid)
        seen.add(pid)


def _assert_snapshot_unchanged(
    *,
    label: str,
    path: Path,
    before: tuple[tuple[str, int], ...],
) -> None:
    after = _snapshot_dir(path)
    if after != before:
        raise AssertionError(
            f"Real {label} changed during test: {path} "
            f"(before={len(before)} files, after={len(after)} files)"
        )


def assert_real_state_untouched(env: IsolatedEnv) -> None:
    _assert_snapshot_unchanged(
        label="Hermes state",
        path=env.real_hermes_path,
        before=env._real_hermes_snapshot,
    )
    _assert_snapshot_unchanged(
        label="IntentFrame Hermes integration state",
        path=env.real_if_hermes_path,
        before=env._real_if_hermes_snapshot,
    )


def assert_no_system_hermes_on_path() -> None:
    if shutil.which("hermes"):
        raise AssertionError("System Hermes is visible on PATH before managed install")


def assert_runtime_stopped(env: IsolatedEnv) -> None:
    artifacts = [
        env.integration_state / "gateway.pid",
        env.integration_state / "adapter.pid",
        env.integration_state / "adapter.sock",
        env.home / ".intentframe" / "backend" / "bridge.pid",
        env.home / ".intentframe" / "backend" / "bridge.sock",
        env.home / ".intentframe" / "backend" / "supervisor.pid",
        env.home / ".intentframe" / "run" / "supervisor.pid",
    ]
    leftovers = [str(path) for path in artifacts if path.exists()]
    if leftovers:
        raise AssertionError("Runtime artifacts left after cleanup:\n" + "\n".join(leftovers))

    alive = [pid for pid in env.tracked_pids if _pid_alive(pid)]
    if alive:
        raise AssertionError(f"Tracked runtime processes still alive: {alive}")


def cleanup_tree(env: IsolatedEnv) -> None:
    shutil.rmtree(env.test_root, ignore_errors=True)
