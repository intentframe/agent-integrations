#!/usr/bin/env bash
# Opt-in live test: GET /v1/toolsets + schema probe after intentframe-gate.
#
#   RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
LIVE_TEST="${REPO_ROOT}/tests/hermes_gateway/test_gateway_toolsets_live.py"

if [[ "${RUN_HERMES_GATEWAY_TOOLSETS:-}" != "1" ]]; then
  echo "SKIP hermes gateway toolsets live test: set RUN_HERMES_GATEWAY_TOOLSETS=1 to run" >&2
  exit 0
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "SKIP hermes gateway toolsets live test: OPENAI_API_KEY not set" >&2
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required but not found on PATH." >&2
  exit 1
fi

(cd "$REPO_ROOT" && uv sync --all-packages --quiet)

exec uv run --with httpx --package intentframe-integrations-cli python "$LIVE_TEST"
