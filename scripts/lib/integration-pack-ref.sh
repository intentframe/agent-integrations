# GitHub archive URL resolution and download for the IntentFrame integration pack.
# Sourced by scripts/install-hermes-plugin.sh (local clone or fetched from raw/{ref}/).

pack_archive_url() {
  local ref="$1"
  local org="$2"
  local repo="$3"

  case "${ref}" in
    refs/heads/*|refs/tags/*)
      printf 'https://github.com/%s/%s/archive/%s.tar.gz' "${org}" "${repo}" "${ref}"
      ;;
    branch/*)
      printf 'https://github.com/%s/%s/archive/refs/heads/%s.tar.gz' \
        "${org}" "${repo}" "${ref#branch/}"
      ;;
    tag/*)
      printf 'https://github.com/%s/%s/archive/refs/tags/%s.tar.gz' \
        "${org}" "${repo}" "${ref#tag/}"
      ;;
    *)
      if [[ "${ref}" =~ ^[0-9a-fA-F]{7,40}$ ]]; then
        printf 'https://github.com/%s/%s/archive/%s.tar.gz' "${org}" "${repo}" "${ref}"
      else
        printf 'branch:%s' "${ref}"
      fi
      ;;
  esac
}

download_integration_pack() {
  local ref="$1"
  local org="$2"
  local repo="$3"
  local dest="$4"
  local tmp=""
  local url=""
  local resolved_url=""

  tmp="$(mktemp)"
  url="$(pack_archive_url "${ref}" "${org}" "${repo}")"

  if [[ "${url}" == branch:* ]]; then
    local bare="${url#branch:}"
    local heads_url tags_url
    heads_url="https://github.com/${org}/${repo}/archive/refs/heads/${bare}.tar.gz"
    tags_url="https://github.com/${org}/${repo}/archive/refs/tags/${bare}.tar.gz"
    if curl -fsSL "${heads_url}" -o "${tmp}" 2>/dev/null; then
      resolved_url="${heads_url}"
    elif curl -fsSL "${tags_url}" -o "${tmp}" 2>/dev/null; then
      resolved_url="${tags_url}"
      if declare -f step >/dev/null 2>&1; then
        step "Resolved ref ${bare} as git tag"
      fi
    else
      echo "ERROR: could not download integration pack for ref=${bare}" >&2
      echo "  tried branch: refs/heads/${bare}" >&2
      echo "  tried tag:    refs/tags/${bare}" >&2
      rm -f "${tmp}"
      return 1
    fi
  else
    resolved_url="${url}"
    if ! curl -fsSL "${resolved_url}" -o "${tmp}"; then
      echo "ERROR: could not download integration pack from ${resolved_url}" >&2
      rm -f "${tmp}"
      return 1
    fi
  fi

  rm -rf "${dest}"
  mkdir -p "${dest}"
  tar -xz -C "${dest}" --strip-components=1 -f "${tmp}"
  rm -f "${tmp}"

  PACK_ARCHIVE_URL="${resolved_url}"
  PACK_REF="${ref}"
  export PACK_ARCHIVE_URL PACK_REF
}

write_install_manifest() {
  local ref="$1"
  local archive_url="$2"
  local org="$3"
  local repo="$4"
  local headless="$5"
  local install_dir="$6"
  local manifest="${install_dir}/.install-manifest.json"
  local installed_at=""
  local headless_json="false"

  installed_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date -u +"%Y-%m-%dT%H:%M:%SZ")"
  if [[ "${headless}" == true ]]; then
    headless_json="true"
  fi

  cat >"${manifest}" <<EOF
{
  "org": "${org}",
  "repo": "${repo}",
  "ref": "${ref}",
  "archive_url": "${archive_url}",
  "installed_at": "${installed_at}",
  "headless": ${headless_json},
  "installer": "install-hermes-plugin.sh"
}
EOF
}

load_integration_pack_ref_lib() {
  local org="$1"
  local repo="$2"
  local ref="$3"
  local local_lib=""

  if [[ "${BASH_SOURCE[0]:-}" == *install-hermes-plugin.sh ]]; then
    local_lib="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/integration-pack-ref.sh"
  elif [[ -n "${INTENTFRAME_INSTALL_LIB:-}" && -f "${INTENTFRAME_INSTALL_LIB}" ]]; then
    local_lib="${INTENTFRAME_INSTALL_LIB}"
  fi

  if [[ -n "${local_lib}" && -f "${local_lib}" ]]; then
    # shellcheck source=scripts/lib/integration-pack-ref.sh
    source "${local_lib}"
    return 0
  fi

  local tmp=""
  tmp="$(mktemp)"
  if ! curl -fsSL \
    "https://github.com/${org}/${repo}/raw/${ref}/scripts/lib/integration-pack-ref.sh" \
    -o "${tmp}"; then
    rm -f "${tmp}"
    echo "ERROR: could not load integration-pack-ref.sh (ref=${ref})" >&2
    return 1
  fi
  # shellcheck source=/dev/null
  source "${tmp}"
  rm -f "${tmp}"
}
