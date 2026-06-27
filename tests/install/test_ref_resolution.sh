#!/usr/bin/env bash
# Unit tests for scripts/lib/integration-pack-ref.sh (pack_archive_url).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export INTENTFRAME_INSTALL_LIB="${ROOT}/scripts/lib/integration-pack-ref.sh"
# shellcheck source=scripts/lib/integration-pack-ref.sh
source "${INTENTFRAME_INSTALL_LIB}"

ORG="intentframe"
REPO="agent-integrations"

assert_eq() {
  local label="$1"
  local got="$2"
  local want="$3"
  if [[ "${got}" != "${want}" ]]; then
    echo "FAIL ${label}" >&2
    echo "  got:  ${got}" >&2
    echo "  want: ${want}" >&2
    exit 1
  fi
}

assert_eq "main branch" \
  "$(pack_archive_url main "${ORG}" "${REPO}")" \
  "branch:main"

assert_eq "feature branch" \
  "$(pack_archive_url feat/install-ref "${ORG}" "${REPO}")" \
  "branch:feat/install-ref"

assert_eq "semver tag (fallback candidate)" \
  "$(pack_archive_url v0.2.0 "${ORG}" "${REPO}")" \
  "branch:v0.2.0"

assert_eq "explicit tag prefix" \
  "$(pack_archive_url tag/v0.2.0 "${ORG}" "${REPO}")" \
  "https://github.com/${ORG}/${REPO}/archive/refs/tags/v0.2.0.tar.gz"

assert_eq "explicit branch prefix" \
  "$(pack_archive_url branch/main "${ORG}" "${REPO}")" \
  "https://github.com/${ORG}/${REPO}/archive/refs/heads/main.tar.gz"

assert_eq "refs/tags" \
  "$(pack_archive_url refs/tags/v0.2.0 "${ORG}" "${REPO}")" \
  "https://github.com/${ORG}/${REPO}/archive/refs/tags/v0.2.0.tar.gz"

assert_eq "refs/heads" \
  "$(pack_archive_url refs/heads/main "${ORG}" "${REPO}")" \
  "https://github.com/${ORG}/${REPO}/archive/refs/heads/main.tar.gz"

SHA="aef66c462abe817e33aad91d97aa782a1e2ad2c7"
assert_eq "commit sha" \
  "$(pack_archive_url "${SHA}" "${ORG}" "${REPO}")" \
  "https://github.com/${ORG}/${REPO}/archive/${SHA}.tar.gz"

assert_eq "short commit sha" \
  "$(pack_archive_url aef66c4 "${ORG}" "${REPO}")" \
  "https://github.com/${ORG}/${REPO}/archive/aef66c4.tar.gz"

echo "OK: pack_archive_url tests passed"
