#!/usr/bin/env bash
# Throwaway Docker smoke: control-plane start on 0.0.0.0 with PID file + fast /api/health.
# Uses local repo tarball (not GitHub install). External probes only — in-process /api/status
# health is covered by tests/intentframe_control_plane/test_server.py.
set -euo pipefail

export HOME="${HOME:-/tmp/cp-smoke-home}"
export INSTALL_DIR="${HOME}/.intentframe/agent-integrations"
export DEBIAN_FRONTEND=noninteractive

step() { printf '\n==> %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

step "Installing OS packages"
apt-get update -qq
apt-get install -y -qq curl ca-certificates
rm -rf /var/lib/apt/lists/*

step "Copy local repo into ${INSTALL_DIR}"
rm -rf "${INSTALL_DIR}"
mkdir -p "${INSTALL_DIR}"
tar -cC /repo --exclude=.git . | tar -xC "${INSTALL_DIR}"

step "Install control plane workspace"
cd "${INSTALL_DIR}"
uv sync --package intentframe-control-plane --package intentframe-integrations-cli

IF_CLI="${INSTALL_DIR}/.venv/bin/intentframe-integrations"
test -x "${IF_CLI}"

step "Seed IntentFrame env for Docker bind"
mkdir -p "${HOME}/.intentframe/logs"
cat >"${HOME}/.intentframe/.env" <<EOF
INTENTFRAME_CONTROL_PLANE_HOST=0.0.0.0
INTENTFRAME_CONTROL_PLANE_PORT=9720
INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE=1
INTENTFRAME_INTEGRATIONS_BIN=${IF_CLI}
EOF

export INTENTFRAME_CONTROL_PLANE_ALLOW_REMOTE=1

step "Start control plane on 0.0.0.0:9720 (background lifecycle)"
if ! "${IF_CLI}" control-plane start --host 0.0.0.0 --port 9720; then
  fail "control-plane start returned non-zero"
fi

step "Verify status reports healthy"
status_out="$("${IF_CLI}" control-plane status)"
echo "${status_out}"
echo "${status_out}" | grep -q "running"
echo "${status_out}" | grep -q "healthy"

step "Verify /api/health responds quickly with PID file present"
if ! command -v curl >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq curl
fi
health_json="$(curl -fsS --max-time 1 http://127.0.0.1:9720/api/health)"
echo "${health_json}" | grep -q '"ok":true\|"ok": true'
echo "${health_json}" | grep -q 'intentframe-control-plane'

step "Verify SPA index is served"
curl -fsS --max-time 2 http://127.0.0.1:9720/ | grep -qi html || true

step "Stop control plane"
"${IF_CLI}" control-plane stop

step "Control plane Docker smoke passed"
