#!/usr/bin/env bash
# Opt-in live test: toolsets + registry schema probe + OpenAI provider tools= payload.
#
# After integrate hermes:
#   1. GET /v1/toolsets (config surface)
#   2. probe_hermes_tool_schemas.py (native governed registry + reason injection)
#   3. POST /v1/responses + HERMES_DUMP_REQUESTS=1 (real chat.completions round-trip)
#   4. Assert token usage > 0 and native governed tools have required reason in tools=
#
#   RUN_HERMES_GATEWAY_TOOLSETS=1 ./tests/scripts/test-hermes-gateway-toolsets.sh
#
# Requires OPENAI_API_KEY. See tests/hermes_gateway/README.md#toolsets--provider-payload-test-opt-in-networked-llm
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
