#!/usr/bin/env bash
# Hermes adapter + plugin integration against live IntentFrame backend.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IF_INTEGRATIONS="${REPO_ROOT}/bin/intentframe-integrations"
ADAPTER_TEST="${REPO_ROOT}/tests/hermes_adapter/test_live.py"
GATE_TEST="${REPO_ROOT}/tests/hermes_plugin/test_bridge_gate_live.py"
ADAPTER_SOCKET="${HOME}/.intentframe/integrations/hermes/adapter.sock"
HERMES_STARTED=0

cleanup() {
  local ec=$?
  if (( HERMES_STARTED )); then
    (cd "$REPO_ROOT" && "$IF_INTEGRATIONS" stop) || true
  fi
  trap - EXIT INT TERM
  exit "$ec"
}
trap cleanup EXIT INT TERM

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "SKIP hermes live integration: OPENAI_API_KEY not set" >&2
  exit 0
fi

(cd "$REPO_ROOT" && "$IF_INTEGRATIONS" stop) || true
(cd "$REPO_ROOT" && "$IF_INTEGRATIONS" start hermes --skip-if-exists)
HERMES_STARTED=1

export IF_AGENT_ADAPTER_SOCKET="${ADAPTER_SOCKET}"
test -S "${ADAPTER_SOCKET}"

(cd "$REPO_ROOT" && uv run --directory integrations/hermes/adapter python "$ADAPTER_TEST")
(cd "$REPO_ROOT" && uv run --with httpx --package intentframe-integrations-cli python "$GATE_TEST")
