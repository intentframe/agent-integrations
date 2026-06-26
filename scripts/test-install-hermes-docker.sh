#!/usr/bin/env bash
# Test install-hermes.sh in Docker: greenfield (no Hermes) and existing Hermes on PATH.
#
# Usage (from repo root, before push):
#   ./scripts/test-install-hermes-docker.sh
#
# Requires: docker
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE="${IMAGE:-ghcr.io/astral-sh/uv:python3.14-bookworm-slim}"
INSTALL_SCRIPT="${REPO_ROOT}/scripts/install-hermes.sh"

step() { printf '\n==> %s\n' "$*"; }

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker is required." >&2
  exit 1
fi

if [[ ! -x "${INSTALL_SCRIPT}" ]]; then
  echo "ERROR: missing ${INSTALL_SCRIPT}" >&2
  exit 1
fi

container_run() {
  docker run --rm \
    -v "${REPO_ROOT}:${REPO_ROOT}:ro" \
    -e "HOME=/root" \
    -e "SKIP_TARBALL=1" \
    -e "INSTALL_DIR=${REPO_ROOT}" \
    "${IMAGE}" \
    bash -lc "$1"
}

apt_bootstrap='
  set -euo pipefail
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq curl tar ca-certificates
  rm -rf /var/lib/apt/lists/*
'

step "Case A: no Hermes on PATH — should install managed Hermes"
container_run "
  ${apt_bootstrap}
  bash ${INSTALL_SCRIPT}
  test -x /root/.intentframe/integrations/hermes/hermes-agent-venv/bin/hermes
  test -d /root/.hermes/plugins/intentframe-gate
  echo 'Case A OK'
"

step "Case B: existing Hermes on PATH — should NOT create managed venv"
container_run "
  ${apt_bootstrap}
  uv venv /opt/hermes-venv --python 3.12 --no-project
  uv pip install --python /opt/hermes-venv/bin/python 'hermes-agent>=0.17.0' -q
  export PATH=/opt/hermes-venv/bin:\${PATH}
  command -v hermes
  hermes --version
  bash ${INSTALL_SCRIPT}
  if test -x /root/.intentframe/integrations/hermes/hermes-agent-venv/bin/hermes; then
    echo 'ERROR: managed Hermes was installed but existing Hermes was on PATH' >&2
    exit 1
  fi
  test -d /root/.hermes/plugins/intentframe-gate
  resolved=\$(/opt/hermes-venv/bin/python - <<'PY'
import os, sys
sys.path.insert(0, '${REPO_ROOT}/intentframe-integrations-cli/src')
os.environ['HOME'] = '/root'
from intentframe_integrations.hermes_install import resolve_hermes_bin
print(resolve_hermes_bin())
PY
)
  case \"\${resolved}\" in
    /opt/hermes-venv/bin/hermes) echo 'Case B OK' ;;
    *) echo \"ERROR: expected /opt/hermes-venv/bin/hermes, got \${resolved}\" >&2; exit 1 ;;
  esac
"

step "All install-hermes Docker tests passed"
