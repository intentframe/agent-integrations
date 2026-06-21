"""Shared Hermes path helpers."""

from __future__ import annotations

import os
from pathlib import Path


def hermes_home() -> Path:
    return Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes")).expanduser()


def hermes_plugins_dir() -> Path:
    return hermes_home() / "plugins"


def hermes_config_path() -> Path:
    return hermes_home() / "config.yaml"
