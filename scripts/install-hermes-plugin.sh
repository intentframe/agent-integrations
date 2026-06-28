#!/usr/bin/env bash
# Install Hermes (if missing) + IntentFrame plugin.
#
# Latest (rolling):
#   curl -fsSL https://github.com/intentframe/agent-integrations/raw/main/scripts/install-hermes-plugin.sh | bash
#
# Pinned release (script URL and pack ref should match):
#   curl -fsSL https://github.com/intentframe/agent-integrations/raw/v0.2.0/scripts/install-hermes-plugin.sh | bash -s -- --ref v0.2.0
#
# Docker / CI (skip Hermes setup wizard + browser engine):
#   curl -fsSL .../install-hermes-plugin.sh | bash -s -- --headless --ref main
#
# Then open IntentFrame Control Plane (auto-started by installer):
#   http://127.0.0.1:9720
#
# Start enforcement stack from Control Plane, then Hermes chat:
#   hermes dashboard            # http://localhost:9119
set -euo pipefail

HEADLESS=false
NO_CONTROL_PLANE=false
NO_OPEN=false
REF="${REF:-}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --headless)
      HEADLESS=true
      shift
      ;;
    --no-control-plane)
      NO_CONTROL_PLANE=true
      shift
      ;;
    --no-open)
      NO_OPEN=true
      shift
      ;;
    --ref)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --ref requires a value" >&2
        exit 1
      fi
      REF="$2"
      shift 2
      ;;
    --ref=*)
      REF="${1#*=}"
      shift
      ;;
    -h|--help)
      cat <<'EOF'
Usage: install-hermes-plugin.sh [--headless] [--no-control-plane] [--no-open] [--ref REF]

  --headless           Skip Hermes setup wizard and browser engine (also skips browser open).
  --no-control-plane   Do not start IntentFrame Control Plane after install (CI/Docker).
  --no-open            Do not open http://127.0.0.1:9720 in a browser after install.

  --ref REF    Git ref for the integration pack (branch, tag, or commit SHA).
               Also set via REF= env. VERSION= is a deprecated alias for REF=.
               Default: main

Install tiers (use the same ref in the script URL and --ref):

  Latest:    curl .../raw/main/scripts/install-hermes-plugin.sh | bash
  Release:   curl .../raw/v0.2.0/... | bash -s -- --ref v0.2.0
  Locked:    curl .../raw/<commit-sha>/... | bash -s -- --ref <commit-sha>
EOF
      exit 0
      ;;
    *)
      echo "Unknown option: $1 (try --help)" >&2
      exit 1
      ;;
  esac
done

if [[ "${HEADLESS}" == true ]]; then
  NO_OPEN=true
fi

ORG="${ORG:-intentframe}"
REPO="${REPO:-agent-integrations}"
REF="${REF:-${VERSION:-main}}"
INSTALL_DIR="${INSTALL_DIR:-${HOME}/.intentframe/agent-integrations}"
LOCAL_BIN="${HOME}/.local/bin"
SYSTEM_BIN="/usr/local/bin"
HERMES_ENV="${HOME}/.hermes/.env"
IF_ENV="${HOME}/.intentframe/.env"
CONTROL_PLANE_URL="http://127.0.0.1:9720"
CLI_SYSTEM=""
HERMES_SUMMARY=""
PACK_REF=""
PACK_ARCHIVE_URL=""

step() { printf '\n==> %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

INTEGRATION_PACK_REF_LIB=""
if [[ -n "${INTENTFRAME_INSTALL_LIB:-}" && -f "${INTENTFRAME_INSTALL_LIB}" ]]; then
  INTEGRATION_PACK_REF_LIB="${INTENTFRAME_INSTALL_LIB}"
elif [[ -n "${BASH_SOURCE:-}" && "${BASH_SOURCE}" != bash* ]]; then
  local_lib="$(cd "$(dirname "${BASH_SOURCE}")" && pwd)/lib/integration-pack-ref.sh"
  if [[ -f "${local_lib}" ]]; then
    INTEGRATION_PACK_REF_LIB="${local_lib}"
  fi
  unset local_lib
fi

if [[ -z "${INTEGRATION_PACK_REF_LIB}" ]]; then
  INTEGRATION_PACK_REF_LIB="$(mktemp)"
  if ! curl -fsSL \
    "https://github.com/${ORG}/${REPO}/raw/${REF}/scripts/lib/integration-pack-ref.sh" \
    -o "${INTEGRATION_PACK_REF_LIB}"; then
    rm -f "${INTEGRATION_PACK_REF_LIB}"
    echo "ERROR: could not load integration-pack-ref.sh (ref=${REF})" >&2
    exit 1
  fi
fi

# shellcheck source=scripts/lib/integration-pack-ref.sh
source "${INTEGRATION_PACK_REF_LIB}"
if [[ "${INTEGRATION_PACK_REF_LIB}" == "${TMPDIR:-/tmp}"/* ]]; then
  rm -f "${INTEGRATION_PACK_REF_LIB}"
fi
unset INTEGRATION_PACK_REF_LIB

ensure_local_bin_on_path() {
  local path_line='export PATH="$HOME/.local/bin:$PATH"'
  local rc
  for rc in "${HOME}/.zshrc" "${HOME}/.bashrc" "${HOME}/.profile"; do
    [[ -f "${rc}" ]] || continue
    grep -qF '.local/bin' "${rc}" && continue
    {
      echo ''
      echo '# Added by IntentFrame Hermes installer'
      echo "${path_line}"
    } >> "${rc}"
  done
  export PATH="${LOCAL_BIN}:${SYSTEM_BIN}:${PATH}"
}

open_browser() {
  local url="$1"
  if [[ "${NO_OPEN}" == true ]]; then
    return 0
  fi
  if [[ -n "${DISPLAY:-}" ]] || [[ "$(uname -s)" == "Darwin" ]]; then
    :
  else
    return 0
  fi
  if [[ "$(uname -s)" == "Darwin" ]] && have open; then
    open "${url}" >/dev/null 2>&1 || true
    return 0
  fi
  if have xdg-open; then
    xdg-open "${url}" >/dev/null 2>&1 || true
  fi
}

seed_intentframe_env() {
  mkdir -p "${HOME}/.intentframe"
  touch "${IF_ENV}"
  for line in \
    "INTENTFRAME_CONTROL_PLANE_HOST=127.0.0.1" \
    "INTENTFRAME_CONTROL_PLANE_PORT=9720" \
    "INTENTFRAME_INTEGRATIONS_BIN=${IF_CLI}"; do
    key="${line%%=*}"
    grep -q "^${key}=" "${IF_ENV}" || echo "${line}" >> "${IF_ENV}"
  done
}

build_control_plane_frontend() {
  local web_dir="${INSTALL_DIR}/intentframe-control-plane/web"
  local static_index="${INSTALL_DIR}/intentframe-control-plane/src/intentframe_control_plane/static/index.html"
  if [[ -f "${static_index}" ]]; then
    return 0
  fi
  if [[ ! -d "${web_dir}" ]]; then
    echo "WARNING: control plane frontend source missing; UI may be unavailable" >&2
    return 0
  fi
  if ! have npm; then
    echo "WARNING: npm not found; skipping control plane frontend build" >&2
    return 0
  fi
  step "Building IntentFrame Control Plane frontend"
  (cd "${web_dir}" && npm ci && npm run build)
}

start_control_plane() {
  if [[ "${NO_CONTROL_PLANE}" == true ]]; then
    return 0
  fi
  step "Starting IntentFrame Control Plane"
  if ! "${IF_CLI}" control-plane start; then
    echo "WARNING: control plane failed to start (port may be in use). Open ${CONTROL_PLANE_URL} manually after: intentframe-integrations control-plane start" >&2
    return 0
  fi
  open_browser "${CONTROL_PLANE_URL}"
}

install_cli_on_path() {
  mkdir -p "${LOCAL_BIN}"
  ln -sf "${IF_CLI}" "${LOCAL_BIN}/intentframe-integrations"

  if [[ "$(id -u)" -eq 0 ]] && [[ ! -d "${SYSTEM_BIN}" ]]; then
    mkdir -p "${SYSTEM_BIN}"
  fi
  if [[ -d "${SYSTEM_BIN}" && ( -w "${SYSTEM_BIN}" || "$(id -u)" -eq 0 ) ]]; then
    ln -sf "${IF_CLI}" "${SYSTEM_BIN}/intentframe-integrations" 2>/dev/null || true
    if [[ -e "${SYSTEM_BIN}/intentframe-integrations" ]]; then
      CLI_SYSTEM="${SYSTEM_BIN}/intentframe-integrations"
    fi
  fi

  ensure_local_bin_on_path
}

# 1. uv
if ! have uv; then
  step "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
export PATH="${HOME}/.local/bin:${PATH}"

# 2. Hermes: use existing, else official install
if have hermes && hermes --version >/dev/null 2>&1; then
  HERMES_VER="$(hermes --version 2>/dev/null || true)"
  step "Using existing Hermes: ${HERMES_VER}"
  HERMES_SUMMARY="Reused existing Hermes (${HERMES_VER})"
else
  if [[ "${HEADLESS}" == true ]]; then
    step "Installing latest Hermes (headless: skip setup wizard + browser engine)"
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-setup --skip-browser
    HERMES_SUMMARY="Installed Hermes 0.17+ (headless — no setup wizard; configure API keys yourself)"
  else
    step "Installing latest Hermes (official installer — full setup)"
    curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
    HERMES_SUMMARY="Installed Hermes (full install — setup wizard runs when needed)"
  fi
  export PATH="${HOME}/.local/bin:${PATH}"
fi

# 3. IntentFrame pack (tarball, no git needed)
step "Downloading IntentFrame integration pack (ref=${REF})"
download_integration_pack "${REF}" "${ORG}" "${REPO}" "${INSTALL_DIR}"
write_install_manifest "${REF}" "${PACK_ARCHIVE_URL}" "${ORG}" "${REPO}" "${HEADLESS}" "${INSTALL_DIR}"
export INTENTFRAME_INTEGRATIONS_ROOT="${INSTALL_DIR}"
cd "${INSTALL_DIR}"

IF_DEV="${INSTALL_DIR}/bin/intentframe-integrations"
IF_CLI="${INSTALL_DIR}/.venv/bin/intentframe-integrations"

step "Installing Python workspace"
uv sync --all-packages

build_control_plane_frontend

step "Installing IntentFrame plugin into Hermes"
"${IF_CLI}" integrate hermes --copy

step "Installing intentframe-integrations on PATH"
install_cli_on_path

# 4. Env so CLI + web + gateway all hit the adapter
step "Writing plugin env to ${HERMES_ENV}"
mkdir -p "${HOME}/.hermes"; touch "${HERMES_ENV}"
for line in \
  "IF_AGENT_ADAPTER_SOCKET=~/.intentframe/integrations/hermes/adapter.sock" \
  "HERMES_GOVERNANCE_YAML=~/.intentframe/integrations/hermes/governance/tools.yaml" \
  "IF_DYNAMIC_BUNDLE_MANIFEST=~/.intentframe/integrations/hermes/governance/generic_actions.manifest"; do
  key="${line%%=*}"
  grep -q "^${key}=" "${HERMES_ENV}" || echo "${line}" >> "${HERMES_ENV}"
done

step "Writing IntentFrame env to ${IF_ENV}"
seed_intentframe_env

start_control_plane

PATH_HINT='intentframe-integrations is on PATH in this shell.'
if ! have intentframe-integrations; then
  PATH_HINT='Open a new terminal, or run: source ~/.zshrc   # if intentframe-integrations is not found'
fi

CLI_LINES="  CLI:     ${LOCAL_BIN}/intentframe-integrations"
if [[ -n "${CLI_SYSTEM}" ]]; then
  CLI_LINES="  CLI:     ${CLI_SYSTEM}
  CLI:     ${LOCAL_BIN}/intentframe-integrations"
fi

HERMES_NEXT=""
if [[ "${HEADLESS}" == true ]]; then
  HERMES_NEXT="
Hermes (headless): run hermes setup if API keys are not configured yet."
fi

CP_LINE="  Control Plane: ${CONTROL_PLANE_URL}"
if [[ "${NO_CONTROL_PLANE}" == true ]]; then
  CP_LINE="  Control Plane: not started (run: intentframe-integrations control-plane start)"
fi

cat <<EOF

Done.

IntentFrame Control Plane:
${CP_LINE}
  Use it to configure keys, start the enforcement stack, manage governed tools, and load policy.

Hermes:
  ${HERMES_SUMMARY}
  Plugin:  ~/.hermes/plugins/intentframe-gate (enabled in ~/.hermes/config.yaml)
  Config:  ~/.hermes/config.yaml
  Env:     ~/.hermes/.env (adapter socket + governance paths)

IntentFrame CLI:
${CLI_LINES}
  Pack:    ${INSTALL_DIR}
  Ref:     ${REF}
  Policy:  ~/.intentframe/integrations/hermes/policy.yaml
  Tools:   ~/.intentframe/integrations/hermes/governance/tools.yaml

Next:
  Open ${CONTROL_PLANE_URL} and start the enforcement stack when ready.
  Hermes chat (separate): hermes dashboard   # http://127.0.0.1:9119/chat
${HERMES_NEXT}

Verify gating:  tail -f ~/.intentframe/integrations/hermes/adapter.log
Verify install: intentframe-integrations doctor hermes

${PATH_HINT}
EOF
