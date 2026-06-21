#!/usr/bin/env bash
# Hermes gateway E2E: full production CLI journey + /v1/responses ALLOW/BLOCK.
#
# Opt-in (slow, networked, LLM-dependent; OPENAI_API_KEY must be in the environment):
#   RUN_HERMES_GATEWAY_E2E=1 ./tests/scripts/test-hermes-gateway-e2e.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
E2E_TEST="${REPO_ROOT}/tests/hermes_gateway/test_gateway_e2e.py"

if [[ "${RUN_HERMES_GATEWAY_E2E:-}" != "1" ]]; then
  echo "SKIP hermes gateway E2E: set RUN_HERMES_GATEWAY_E2E=1 to run" >&2
  exit 0
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "SKIP hermes gateway E2E: OPENAI_API_KEY not set" >&2
  exit 0
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "ERROR: uv is required but not found on PATH." >&2
  exit 1
fi

(cd "$REPO_ROOT" && uv sync --all-packages --quiet)

exec uv run --with httpx --package intentframe-integrations-cli python "$E2E_TEST"
