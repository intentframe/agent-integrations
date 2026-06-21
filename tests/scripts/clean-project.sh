#!/usr/bin/env bash
# Remove local dev artifacts for agent-integrations (uv workspace + npm workspaces).
# Optionally stops the backend runtime and clears ~/.intentframe state.
#
# Usage:
#   ./scripts/clean-project.sh
#   ./scripts/clean-project.sh --keep-runtime
#   ./scripts/clean-project.sh --dry-run
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/if-integration-backend"
PY_CLIENT_DIR="${REPO_ROOT}/if-integration-clients/python"
TS_CLIENT_DIR="${REPO_ROOT}/if-integration-clients/typescript"
INTENTFRAME_STATE="${HOME}/.intentframe/backend"
INTENTFRAME_RUN="${HOME}/.intentframe/run"

KEEP_RUNTIME=0
DRY_RUN=0

usage() {
  cat <<'EOF'
Usage: clean-project.sh [OPTIONS]

Remove local Python/npm build artifacts created by development and e2e tests.
By default also stops if-integration-backend and clears ~/.intentframe runtime state.

Options:
  --keep-runtime   Remove repo venvs/node_modules only; do not touch ~/.intentframe
  --dry-run        Print what would be removed without deleting anything
  -h, --help       Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --keep-runtime) KEEP_RUNTIME=1 ;;
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "ERROR: unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

if git -C "$REPO_ROOT" rev-parse --show-toplevel >/dev/null 2>&1; then
  REPO_ROOT="$(git -C "$REPO_ROOT" rev-parse --show-toplevel)"
fi

step() { printf '==> %s\n' "$*"; }

remove_path() {
  local path=$1
  if [[ -e "$path" || -L "$path" ]]; then
    if (( DRY_RUN )); then
      printf '[dry-run] rm -rf %q\n' "$path"
    else
      rm -rf "$path"
    fi
  fi
}

remove_pycache_under() {
  local dir=$1
  [[ -d "$dir" ]] || return 0
  if (( DRY_RUN )); then
    while IFS= read -r -d '' path; do
      printf '[dry-run] rm -rf %q\n' "$path"
    done < <(find "$dir" -type d -name __pycache__ -print0 2>/dev/null)
  else
    find "$dir" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
  fi
}

step "Stop if-integration-backend runtime (if installed)"
if [[ -d "$BACKEND_DIR" ]] && command -v uv >/dev/null 2>&1; then
  if (( DRY_RUN )); then
    printf '[dry-run] (cd %q && uv run --package if-integration-backend if-integration-backend stop) || true\n' "$REPO_ROOT"
  else
    (cd "$REPO_ROOT" && uv run --package if-integration-backend if-integration-backend stop) 2>/dev/null || true
  fi
else
  echo "    skipped (backend dir or uv not available)"
fi

step "Remove Python virtualenvs (workspace + legacy member venvs)"
remove_path "${REPO_ROOT}/.venv"
remove_path "${BACKEND_DIR}/.venv"
remove_path "${PY_CLIENT_DIR}/.venv"
remove_pycache_under "${PY_CLIENT_DIR}/src"
remove_pycache_under "${BACKEND_DIR}/src"

step "Remove npm workspace install and TypeScript build output"
remove_path "${REPO_ROOT}/node_modules"
remove_path "${TS_CLIENT_DIR}/node_modules"
remove_path "${TS_CLIENT_DIR}/dist"

if (( KEEP_RUNTIME )); then
  step "Keeping ~/.intentframe runtime state (--keep-runtime)"
else
  step "Remove IntentFrame runtime state"
  remove_path "$INTENTFRAME_STATE"
  remove_path "$INTENTFRAME_RUN"
fi

step "Done"
if (( DRY_RUN )); then
  echo "Dry run only — no files were changed."
else
  echo "Project cleanup complete. Run ./scripts/e2e.sh for a fresh e2e test."
fi
