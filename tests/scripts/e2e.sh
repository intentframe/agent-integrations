#!/usr/bin/env bash
# Self-contained end-to-end test for agent-integrations (monorepo workspace).
# Runtime lifecycle goes through bin/intentframe-integrations (orchestrator → backend).
#
# Prerequisites (must already be on PATH):
#   - node + npm
#   - curl (only if uv is missing; used to bootstrap uv)
#
# OPENAI_API_KEY must already be in the environment (e.g. VS Code terminal settings).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
IF_INTEGRATIONS="${REPO_ROOT}/bin/intentframe-integrations"
AGENTS_DIR="${REPO_ROOT}/tests/agents"
EXAMPLES_PY="${REPO_ROOT}/tests/examples/python/test_validate.py"
EXAMPLES_TS="${REPO_ROOT}/tests/examples/typescript/test_validate.mjs"
TS_CLIENT_DIST="${REPO_ROOT}/if-integration-clients/typescript/dist/index.js"
BRIDGE_SOCKET="${HOME}/.intentframe/backend/bridge.sock"
RUNTIME_STARTED=0

step() { printf '\n==> %s\n' "$*"; }

if_cli() {
  (cd "$REPO_ROOT" && "$IF_INTEGRATIONS" "$@")
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "ERROR: '$1' is required but not found on PATH." >&2
    exit 1
  fi
}

ensure_uv() {
  if command -v uv >/dev/null 2>&1; then
    return 0
  fi
  require_cmd curl
  step "Installing uv (not found on PATH)"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
  if ! command -v uv >/dev/null 2>&1; then
    echo "ERROR: uv install finished but 'uv' is still not on PATH." >&2
    echo "Add ~/.local/bin to PATH and re-run this script." >&2
    exit 1
  fi
}

resolve_repo_root() {
  if git -C "$REPO_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
    REPO_ROOT="$(git -C "$REPO_ROOT" rev-parse --show-toplevel)"
  fi
}

cleanup() {
  local ec=$?
  if (( RUNTIME_STARTED )); then
    step "Stop everything (cleanup)"
    if_cli stop || true
    RUNTIME_STARTED=0
  fi
  trap - EXIT INT TERM
  exit "$ec"
}
trap cleanup EXIT INT TERM

resolve_repo_root

if [[ ! -x "$IF_INTEGRATIONS" ]]; then
  echo "ERROR: intentframe-integrations launcher not found: ${IF_INTEGRATIONS}" >&2
  exit 1
fi

if [[ ! -d "${REPO_ROOT}/if-integration-backend" ]]; then
  echo "ERROR: if-integration-backend not found under ${REPO_ROOT}" >&2
  exit 1
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "ERROR: OPENAI_API_KEY is not set." >&2
  echo "Use a VS Code/Cursor integrated terminal (see .vscode/settings.json) or export it in your shell." >&2
  exit 1
fi

export INTENTFRAME_USER_ID="${INTENTFRAME_USER_ID:-test_user}"

step "Check prerequisites"
require_cmd node
require_cmd npm
ensure_uv

step "Install Python workspace (uv sync --all-packages)"
(cd "$REPO_ROOT" && uv sync --all-packages)

step "Install npm workspaces and build TypeScript bridge client"
(cd "$REPO_ROOT" && npm install && npm run build)
if [[ ! -f "$TS_CLIENT_DIST" ]]; then
  echo "ERROR: TypeScript bridge client build failed (missing ${TS_CLIENT_DIST})" >&2
  exit 1
fi

step "Stop everything (core + bridge + sockets)"
if_cli stop || true

step "Start core + executor + bridge (tests/agents)"
RUNTIME_STARTED=1
if_cli start --agent-config "$AGENTS_DIR" --no-seed

step "Seed policies for each e2e agent"
for agent_json in "$AGENTS_DIR"/*/agent.json; do
  if_cli seed --agent-config "$agent_json" --skip-if-exists
done

step "Status"
if_cli status
test -S "$BRIDGE_SOCKET"

step "Backend integration tests (core Actor + bridge HTTP)"
if_cli test

step "Python bridge client example"
export IF_AGENT_BRIDGE_SECRET="test-bridge-python-secret-dev-only"
export IF_SECURITY_BRIDGE_SOCKET="$BRIDGE_SOCKET"
(cd "$REPO_ROOT" && uv run --package if-integration-bridge-client python "$EXAMPLES_PY")

step "TypeScript bridge client example"
export IF_AGENT_BRIDGE_SECRET="test-bridge-typescript-secret-dev-only"
export IF_SECURITY_BRIDGE_SOCKET="$BRIDGE_SOCKET"
(cd "$REPO_ROOT" && node "$EXAMPLES_TS")

step "Hermes adapter unit tests"
(cd "$REPO_ROOT" && uv run --directory integrations/hermes/adapter python tests/test_adapter.py)

step "Hermes plugin unit tests"
(cd "$REPO_ROOT" && uv run --with httpx --package intentframe-integrations-cli python tests/hermes_plugin/test_gate.py)
(cd "$REPO_ROOT" && uv run --package intentframe-integrations-cli python tests/hermes_plugin/test_integrate.py)

step "Integrations CLI unit tests"
(cd "$REPO_ROOT" && uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_runtime_lifecycle.py)
(cd "$REPO_ROOT" && uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_integration_pack.py)
(cd "$REPO_ROOT" && uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_cli_start.py)
(cd "$REPO_ROOT" && uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_adapter_lifecycle.py)
(cd "$REPO_ROOT" && uv run --package intentframe-integrations-cli python tests/intentframe_integrations/test_hermes_install.py)

step "Hermes live integration (adapter + plugin gate)"
bash "${SCRIPT_DIR}/test-hermes-integration.sh"

step "All e2e checks passed"
