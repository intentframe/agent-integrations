#!/usr/bin/env bash
# Regression test for the curl-piped installer bootstrap path.
#
# The real installer is fed through stdin, so BASH_SOURCE[0] is not the repo
# script path. A mocked curl serves the helper lib and pack archive from inside
# the container, proving the installer can source its helper before using it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
IMAGE="${INSTALLER_BOOTSTRAP_DOCKER_IMAGE:-ghcr.io/astral-sh/uv:python3.14-bookworm-slim}"

docker run --rm \
  -v "${ROOT}:/repo:ro" \
  -w /repo \
  "${IMAGE}" \
  bash -lc '
set -euo pipefail

export HOME=/tmp/if-home
export INSTALL_DIR="${HOME}/.intentframe/agent-integrations"
mkdir -p "${HOME}" /tmp/bin /tmp/pkg/agent-integrations-test-ref

cp /repo/scripts/lib/integration-pack-ref.sh /tmp/integration-pack-ref.sh
tar -czf /tmp/pack.tar.gz -C /tmp/pkg agent-integrations-test-ref

cat >/tmp/bin/hermes <<'"'"'EOF'"'"'
#!/usr/bin/env bash
if [[ "${1:-}" == "--version" ]]; then
  echo "hermes 0.17.0"
fi
EOF
chmod +x /tmp/bin/hermes

cat >/tmp/bin/uv <<'"'"'EOF'"'"'
#!/usr/bin/env bash
if [[ "${1:-}" == "sync" ]]; then
  mkdir -p .venv/bin
  cat >.venv/bin/intentframe-integrations <<'"'"'EOS'"'"'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == "integrate" && "${2:-}" == "hermes" ]]; then
  mkdir -p "${HOME}/.hermes/plugins/intentframe-gate"
  printf "name: intentframe-gate\n" >"${HOME}/.hermes/plugins/intentframe-gate/plugin.yaml"
  mkdir -p "${HOME}/.intentframe/integrations/hermes/governance"
  : >"${HOME}/.intentframe/integrations/hermes/governance/tools.yaml"
  : >"${HOME}/.intentframe/integrations/hermes/governance/generic_actions.manifest"
  : >"${HOME}/.intentframe/integrations/hermes/policy.yaml"
  exit 0
fi
if [[ "${1:-}" == "--version" ]]; then
  echo "intentframe-integrations test"
  exit 0
fi
echo "unexpected intentframe-integrations args: $*" >&2
exit 1
EOS
  chmod +x .venv/bin/intentframe-integrations
  exit 0
fi
echo "unexpected uv args: $*" >&2
exit 1
EOF
chmod +x /tmp/bin/uv

cat >/tmp/bin/curl <<'"'"'EOF'"'"'
#!/usr/bin/env bash
set -euo pipefail

out=""
url=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o)
      out="$2"
      shift 2
      ;;
    -*)
      shift
      ;;
    *)
      url="$1"
      shift
      ;;
  esac
done

if [[ "${url}" == "https://github.com/intentframe/agent-integrations/raw/test-ref/scripts/lib/integration-pack-ref.sh" ]]; then
  if [[ -n "${out}" ]]; then
    cp /tmp/integration-pack-ref.sh "${out}"
  else
    cat /tmp/integration-pack-ref.sh
  fi
  exit 0
fi

if [[ "${url}" == "https://github.com/intentframe/agent-integrations/archive/refs/heads/test-ref.tar.gz" ]]; then
  cp /tmp/pack.tar.gz "${out}"
  exit 0
fi

echo "unexpected curl url: ${url}" >&2
exit 1
EOF
chmod +x /tmp/bin/curl

export PATH="/tmp/bin:${PATH}"
bash -s -- --headless --no-control-plane --ref test-ref </repo/scripts/install-hermes-plugin.sh

export PATH="${HOME}/.local/bin:${PATH}"
command -v intentframe-integrations
intentframe-integrations --version
python -m json.tool "${INSTALL_DIR}/.install-manifest.json"
test -f "${HOME}/.hermes/plugins/intentframe-gate/plugin.yaml"
test -f "${HOME}/.hermes/.env"
'
