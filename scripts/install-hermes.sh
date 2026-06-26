#!/usr/bin/env bash
# Public installer: IntentFrame plugin + adapter stack for Hermes Agent.
#
# Uses existing `hermes` on PATH when present (any version). Otherwise installs
# a pinned managed Hermes Agent under ~/.intentframe/integrations/hermes/.
#
# Usage:
#   curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes.sh | bash
#
# Pin a release tag (after you publish one):
#   VERSION=v0.2.0 bash -c "$(curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes.sh)"
#
# Options (env):
#   VERSION       Git tag (default: main branch tarball)
#   INSTALL_DIR   Where to unpack (default: ~/.intentframe/agent-integrations)
#   SKIP_TARBALL  Set to 1 to use INSTALL_DIR as an existing checkout (tests/local)
#   ORG           GitHub org (default: intentframe)
#   REPO          GitHub repo (default: agent-integrations)
set -euo pipefail

ORG="${ORG:-intentframe}"
REPO="${REPO:-agent-integrations}"
VERSION="${VERSION:-main}"
INSTALL_DIR="${INSTALL_DIR:-${HOME}/.intentframe/agent-integrations}"

step() { printf '\n==> %s\n' "$*"; }

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

find_hermes_cli() {
  local candidate=""
  if [[ -n "${HERMES_BIN:-}" ]] && [[ -x "${HERMES_BIN}" ]]; then
    candidate="${HERMES_BIN}"
  elif command -v hermes >/dev/null 2>&1; then
    candidate="$(command -v hermes)"
  else
    return 1
  fi
  if "${candidate}" --version >/dev/null 2>&1; then
    printf '%s\n' "${candidate}"
    return 0
  fi
  return 1
}

tarball_url() {
  if [[ "${VERSION}" == "main" ]]; then
    printf 'https://github.com/%s/%s/archive/refs/heads/main.tar.gz' "${ORG}" "${REPO}"
  else
    printf 'https://github.com/%s/%s/archive/refs/tags/%s.tar.gz' "${ORG}" "${REPO}" "${VERSION}"
  fi
}

step "Checking prerequisites"
require_cmd curl
ensure_uv

if [[ "${SKIP_TARBALL:-}" == "1" ]]; then
  step "Using local tree at ${INSTALL_DIR}"
  if [[ ! -x "${INSTALL_DIR}/bin/intentframe-integrations" ]]; then
    echo "ERROR: SKIP_TARBALL=1 but launcher missing: ${INSTALL_DIR}/bin/intentframe-integrations" >&2
    exit 1
  fi
else
  require_cmd tar
  TARBALL="$(tarball_url)"
  step "Downloading IntentFrame Hermes pack (${VERSION})"
  step "  ${TARBALL}"
  rm -rf "${INSTALL_DIR}"
  mkdir -p "${INSTALL_DIR}"
  curl -fsSL "${TARBALL}" | tar -xz -C "${INSTALL_DIR}" --strip-components=1
fi

export INTENTFRAME_INTEGRATIONS_ROOT="${INSTALL_DIR}"
cd "${INSTALL_DIR}"

IF_INTEGRATIONS="${INSTALL_DIR}/bin/intentframe-integrations"

step "Installing Python workspace (uv sync --all-packages)"
uv sync --all-packages

HERMES_SOURCE="managed"
if existing_hermes="$(find_hermes_cli)"; then
  step "Using existing Hermes CLI: ${existing_hermes}"
  hermes_version="$("${existing_hermes}" --version 2>/dev/null || echo unknown)"
  step "  version: ${hermes_version}"
  HERMES_SOURCE="existing"
else
  step "No Hermes CLI found — installing managed Hermes Agent"
  "${IF_INTEGRATIONS}" install hermes
fi

step "Installing IntentFrame Hermes plugin and adapter"
"${IF_INTEGRATIONS}" integrate hermes --copy

step "Verifying install"
"${IF_INTEGRATIONS}" doctor hermes --install-only

cat <<EOF

IntentFrame Hermes install complete.

Install root:  ${INSTALL_DIR}
Launcher:      ${IF_INTEGRATIONS}
Hermes source: ${HERMES_SOURCE}

Start Hermes (requires OPENAI_API_KEY):
  export OPENAI_API_KEY=sk-...
  ${IF_INTEGRATIONS} run hermes

Governed tools (terminal, write_file, patch, etc.) go through IntentFrame when
you start via intentframe-integrations run hermes (adapter + backend + plugin env).

Optional: add launcher to PATH
  export PATH="${INSTALL_DIR}/bin:\${PATH}"
EOF
