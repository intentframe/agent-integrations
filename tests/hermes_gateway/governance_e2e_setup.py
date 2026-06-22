"""Governance yaml setup for Hermes gateway LLM E2E (temp file, optional tool scoping)."""

from __future__ import annotations

import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CLI_SRC = _REPO_ROOT / "intentframe-integrations-cli" / "src"
_TESTS_DIR = _REPO_ROOT / "tests"
_SHARED_SRC = _REPO_ROOT / "integrations" / "hermes" / "shared" / "src"
for path in (_CLI_SRC, _TESTS_DIR, _SHARED_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from intentframe_integrations.hermes_governance_contract import (  # noqa: E402
    write_scoped_governance_yaml,
)
from hermes_governance_fixtures import (  # noqa: E402
    GATEWAY_E2E_PROBE_SYMBOLS,
    clear_shared_governance_cache,
    template_catalog_tool_names,
)
from hermes_governance.loader import load_governed_tools, load_tool_catalog  # noqa: E402

_E2E_GOV_YAML_DIR: Path | None = None
_E2E_GOVERNED_TOOLS_ENV = "HERMES_E2E_GOVERNED_TOOLS"


@dataclass(frozen=True)
class GovernanceSnapshot:
    yaml_path: Path
    catalog: frozenset[str]
    governed: frozenset[str]
    ungoverned: frozenset[str]
    governed_via_env: frozenset[str] | None
    auto_generated: bool


def parse_governed_tools_env(raw: str) -> frozenset[str]:
    """Parse comma-separated IntentFrame-governed tool names from E2E env."""
    names = frozenset(part.strip() for part in raw.split(",") if part.strip())
    if not names:
        raise ValueError(f"{_E2E_GOVERNED_TOOLS_ENV} must list at least one governed tool")
    return names


def load_e2e_governance_snapshot() -> GovernanceSnapshot:
    """Read the active E2E governance yaml and governed/ungoverned tool sets."""
    yaml_str = os.environ.get("HERMES_GOVERNANCE_YAML", "").strip()
    if not yaml_str:
        raise AssertionError(
            "HERMES_GOVERNANCE_YAML is not set — call setup_e2e_governance_yaml() first"
        )

    yaml_path = Path(yaml_str).expanduser()
    if not yaml_path.is_file():
        raise AssertionError(f"HERMES_GOVERNANCE_YAML points to missing file: {yaml_path}")

    clear_shared_governance_cache()
    catalog = frozenset(load_tool_catalog().keys())
    governed = frozenset(load_governed_tools().keys())
    ungoverned = catalog - governed

    governed_raw = os.environ.get(_E2E_GOVERNED_TOOLS_ENV, "").strip()
    governed_via_env = parse_governed_tools_env(governed_raw) if governed_raw else None

    auto_generated = (
        _E2E_GOV_YAML_DIR is not None and yaml_path.parent.resolve() == _E2E_GOV_YAML_DIR.resolve()
    )

    return GovernanceSnapshot(
        yaml_path=yaml_path,
        catalog=catalog,
        governed=governed,
        ungoverned=ungoverned,
        governed_via_env=governed_via_env,
        auto_generated=auto_generated,
    )


def assert_e2e_governance_snapshot(snapshot: GovernanceSnapshot) -> None:
    """Fail fast when env scoping and runtime yaml disagree."""
    if not snapshot.governed:
        raise AssertionError(
            "Governance yaml must have at least one IntentFrame-governed tool"
        )

    unknown = snapshot.governed - snapshot.catalog
    if unknown:
        raise AssertionError(
            f"Runtime governed tools not in catalog: {sorted(unknown)} "
            f"(catalog: {sorted(snapshot.catalog)})"
        )

    if snapshot.governed_via_env is not None and snapshot.governed != snapshot.governed_via_env:
        raise AssertionError(
            "HERMES_E2E_GOVERNED_TOOLS does not match runtime governed set.\n"
            f"  HERMES_E2E_GOVERNED_TOOLS: {sorted(snapshot.governed_via_env)}\n"
            f"  runtime governed:          {sorted(snapshot.governed)}\n"
            f"  yaml: {snapshot.yaml_path}"
        )

    catalog_tools = template_catalog_tool_names()
    if snapshot.catalog != catalog_tools:
        raise AssertionError(
            "E2E governance catalog differs from default template catalog.\n"
            f"  yaml catalog:      {sorted(snapshot.catalog)}\n"
            f"  template catalog:  {sorted(catalog_tools)}"
        )


def format_governance_snapshot(snapshot: GovernanceSnapshot) -> str:
    lines = [
        "IntentFrame governance snapshot (plugin gate — not Hermes toolsets):",
        f"  HERMES_GOVERNANCE_YAML: {snapshot.yaml_path}",
        f"  auto_generated_temp: {snapshot.auto_generated}",
        f"  catalog ({len(snapshot.catalog)}): {sorted(snapshot.catalog)}",
        f"  governed by IntentFrame ({len(snapshot.governed)}): {sorted(snapshot.governed)}",
        f"  not governed — native Hermes ({len(snapshot.ungoverned)}): {sorted(snapshot.ungoverned)}",
    ]
    if snapshot.governed_via_env is not None:
        lines.append(
            f"  HERMES_E2E_GOVERNED_TOOLS: {sorted(snapshot.governed_via_env)}"
        )
    else:
        lines.append(
            "  HERMES_E2E_GOVERNED_TOOLS: (unset — all catalog tools governed)"
        )
    return "\n".join(lines)


def format_gateway_probe_plan(governed: frozenset[str]) -> str:
    lines = ["LLM probe plan (IntentFrame-governed → RUN, not governed → SKIP):"]
    for tool in sorted(template_catalog_tool_names()):
        probes = sorted(GATEWAY_E2E_PROBE_SYMBOLS.get(tool, ()))
        if tool in governed:
            lines.append(f"  {tool}: RUN  probes={probes}")
        else:
            lines.append(f"  {tool}: SKIP probes={probes}")
    return "\n".join(lines)


def assert_governance_env_contract(*, label: str = "runtime") -> GovernanceSnapshot:
    """Assert os.environ and CLI-built child env agree on HERMES_GOVERNANCE_YAML."""
    snapshot = load_e2e_governance_snapshot()
    actual = os.environ.get("HERMES_GOVERNANCE_YAML", "").strip()
    if not actual:
        raise AssertionError(f"{label}: HERMES_GOVERNANCE_YAML must be set before start")

    if Path(actual).expanduser().resolve() != snapshot.yaml_path.resolve():
        raise AssertionError(
            f"{label}: HERMES_GOVERNANCE_YAML path mismatch.\n"
            f"  env:      {actual}\n"
            f"  snapshot: {snapshot.yaml_path}"
        )

    from intentframe_integrations.adapter_lifecycle import _adapter_env
    from intentframe_integrations.hermes_gateway import build_gateway_env
    from intentframe_integrations.hermes_integrate import load_hermes_pack

    pack = load_hermes_pack()
    gateway_gov = build_gateway_env(pack).get("HERMES_GOVERNANCE_YAML", "")
    if gateway_gov != actual:
        raise AssertionError(
            f"{label}: build_gateway_env HERMES_GOVERNANCE_YAML differs from os.environ.\n"
            f"  os.environ:         {actual}\n"
            f"  build_gateway_env:  {gateway_gov}"
        )

    adapter_gov = _adapter_env(pack).get("HERMES_GOVERNANCE_YAML", "")
    if adapter_gov != actual:
        raise AssertionError(
            f"{label}: _adapter_env HERMES_GOVERNANCE_YAML differs from os.environ.\n"
            f"  os.environ:    {actual}\n"
            f"  _adapter_env:  {adapter_gov}"
        )

    return snapshot


def log_e2e_governance(*, log: Callable[[str], None]) -> GovernanceSnapshot:
    snapshot = load_e2e_governance_snapshot()
    assert_e2e_governance_snapshot(snapshot)
    log(format_governance_snapshot(snapshot))
    log(format_gateway_probe_plan(snapshot.governed))
    return snapshot


def setup_e2e_governance_yaml(*, log: Callable[[str], None] | None = None) -> Path:
    """Materialize temp governance yaml unless HERMES_GOVERNANCE_YAML is already set."""
    global _E2E_GOV_YAML_DIR

    existing = os.environ.get("HERMES_GOVERNANCE_YAML", "").strip()
    if existing:
        path = Path(existing).expanduser()
        if log:
            log(f"Using existing HERMES_GOVERNANCE_YAML={path}")
    else:
        governed_raw = os.environ.get(_E2E_GOVERNED_TOOLS_ENV, "").strip()
        governed_tools = parse_governed_tools_env(governed_raw) if governed_raw else None

        path = write_scoped_governance_yaml(governed_tools=governed_tools)
        _E2E_GOV_YAML_DIR = path.parent
        os.environ["HERMES_GOVERNANCE_YAML"] = str(path)

        if log:
            if governed_tools is None:
                log(f"Wrote temp governance yaml (all catalog tools governed): {path}")
            else:
                log(
                    f"Wrote temp governance yaml "
                    f"(HERMES_E2E_GOVERNED_TOOLS={sorted(governed_tools)}): {path}"
                )

    if log:
        log_e2e_governance(log=log)
    else:
        assert_e2e_governance_snapshot(load_e2e_governance_snapshot())

    return path


def cleanup_e2e_governance_yaml() -> None:
    global _E2E_GOV_YAML_DIR
    if _E2E_GOV_YAML_DIR is not None and _E2E_GOV_YAML_DIR.is_dir():
        shutil.rmtree(_E2E_GOV_YAML_DIR, ignore_errors=True)
    _E2E_GOV_YAML_DIR = None
