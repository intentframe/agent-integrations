#!/usr/bin/env bash
# CI smoke: headless install path inside Docker using the local repo pack.
#
# Exercises real `uv sync --all-packages` (PyPI IntentFrame deps) and
# `integrate hermes` without OPENAI_API_KEY or the full Hermes installer.
# Hermes CLI is stubbed; the integration pack and Python workspace are real.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${HEADLESS_INSTALL_SMOKE_IMAGE:-ghcr.io/astral-sh/uv:python3.14-bookworm-slim}"

docker run --rm \
  -v "${ROOT}:/repo:ro" \
  -w /repo \
  "${IMAGE}" \
  bash /repo/tests/docker/headless_install_smoke_inner.sh
