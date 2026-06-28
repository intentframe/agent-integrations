#!/usr/bin/env bash
# Run control-plane lifecycle smoke in a throwaway container (local repo, no Hermes install).
# Verifies: start on 0.0.0.0, external health probe, /api/status, SPA index, stop.
# See tests/docker/control_plane_smoke_inner.sh and tests/docker/README.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${CONTROL_PLANE_SMOKE_IMAGE:-ghcr.io/astral-sh/uv:python3.14-bookworm-slim}"

docker run --rm \
  -v "${ROOT}:/repo:ro" \
  -w /repo \
  "${IMAGE}" \
  bash /repo/tests/docker/control_plane_smoke_inner.sh
