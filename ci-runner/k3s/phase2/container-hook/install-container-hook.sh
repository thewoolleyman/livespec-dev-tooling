#!/usr/bin/env bash
# install-container-hook.sh — NODE-LOCAL (root): install the fleet-patched ARC
# Kubernetes container hook that build-patched-hook.sh produced for the pinned
# runner image, then extract that image's externals beside the runner work
# volumes (./extract-externals.sh). Run by ../install-node.sh (step 7c, after
# the other /usr/local/lib/ci-runner-k3s installs and BEFORE the reconstruct
# artifacts are copied, since the values files the boot converge applies name
# the path installed here). Re-run after a runner-image bump — which first
# needs a rebuild on a developer host (README.md "Runner-image bump").
#
# WHAT LANDS:
#   /usr/local/lib/ci-runner-k3s/hooks/<runner-version>/index.js   0644 root
#   /usr/local/lib/ci-runner-k3s/hooks/<runner-version>/index.js.sha256
#   /usr/local/lib/ci-runner-k3s/hooks/<runner-version>/BUILD-INFO
#   <storage-root>/.externals/<runner-version>/ (+ marker) via extract-externals.sh
# The runner pod runs as uid 1000 and reads the hook through a read-only
# hostPath mount, so 0644 root-owned is exactly enough. Per-version directories
# let a bump stage the new hook before any values file selects it.
#
# WHAT SELECTS IT (the second half of livespec-wm7c, in ../arc/values-*.yaml,
# after livespec-lvtu lands): a hostPath mount of that directory into the
# runner container, ACTIONS_RUNNER_CONTAINER_HOOKS=<mount>/index.js (the chart
# yields to a user-supplied value of that env), and
# ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION=<runner-version> — together with
# the provisioner setup seed of ${VOL_DIR}/externals from the extracted copy.
# Those three MUST land together: a seed with no env means the upstream copy
# runs over hardlinked files it cannot write; an env with no seed is harmless
# (no marker, so the copy runs).
#
# Idempotent: skips the copy when the installed bundle already matches the
# manifest; extract-externals.sh is idempotent on its own manifest.
#
# Usage: install-container-hook.sh [--image <ref>] [--storage-root <dir>]
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CONTAINER_HOOK_DIR="${SCRIPT_DIR}"
# shellcheck source=./runner-image.sh
source "${SCRIPT_DIR}/runner-image.sh"

HOOKS_ROOT="/usr/local/lib/ci-runner-k3s/hooks"
USAGE="usage: install-container-hook.sh [--image <ref>] [--storage-root <dir>]"
image=""
storage_root="/var/lib/rancher/k3s/storage"
while [ $# -gt 0 ]; do
  case "$1" in
    --image) image="${2:?--image needs a value}"; shift 2 ;;
    --storage-root) storage_root="${2:?--storage-root needs a value}"; shift 2 ;;
    -h|--help) echo "${USAGE}"; exit 0 ;;
    *) echo "FATAL: unknown argument '$1'" >&2; echo "${USAGE}" >&2; exit 1 ;;
  esac
done

log() { printf '\n== %s ==\n' "$*"; }
die() { echo "FATAL: $*" >&2; exit 1; }

[ "$(id -u)" -eq 0 ] || die "must run as root (writes ${HOOKS_ROOT})"
command -v sha256sum >/dev/null || die "sha256sum not on PATH"

image="$(resolve_runner_image "${image}")"
runner_version="$(runner_version_from_ref "${image}")"
digest_ref="$(digest_ref_from_ref "${image}")"
bundle="${SCRIPT_DIR}/bundle/${runner_version}"
dest="${HOOKS_ROOT}/${runner_version}"

# ---------------------------------------------------------------------------
log "1. The committed bundle for runner ${runner_version}"
for f in index.js index.js.sha256 BUILD-INFO; do
  [ -f "${bundle}/${f}" ] || die "${bundle}/${f} missing — run build-patched-hook.sh for this runner image and commit its output (README.md \"Runner-image bump\")"
done
( cd "${bundle}" && sha256sum -c --quiet index.js.sha256 ) || die "${bundle}/index.js does not match its manifest"
built_for="$(sed -n 's/^runner_image_digest_ref=//p' "${bundle}/BUILD-INFO")"
[ "${built_for}" = "${digest_ref}" ] || die "the bundle was built for ${built_for}, not the pinned ${digest_ref} — rebuild"
upstream_sha="$(sed -n 's/^upstream_index_js_sha256=//p' "${bundle}/BUILD-INFO")"
[[ "${upstream_sha}" =~ ^[0-9a-f]{64}$ ]] || die "BUILD-INFO carries no upstream_index_js_sha256"
bundle_sha="$(cut -d' ' -f1 "${bundle}/index.js.sha256")"
echo "bundle:   ${bundle}/index.js (sha256 ${bundle_sha})"
echo "built for ${built_for}; upstream hook sha256 ${upstream_sha}"

# ---------------------------------------------------------------------------
log "2. Install ${dest}"
if [ -f "${dest}/index.js" ] && [ "$(sha256sum "${dest}/index.js" | cut -d' ' -f1)" = "${bundle_sha}" ]; then
  echo "already installed (sha256 matches)"
else
  install -d -m 0755 "${HOOKS_ROOT}" "${dest}"
  install -o root -g root -m 0644 "${bundle}/index.js" "${dest}/index.js"
  echo "installed ${dest}/index.js"
fi
install -o root -g root -m 0644 "${bundle}/index.js.sha256" "${dest}/index.js.sha256"
install -o root -g root -m 0644 "${bundle}/BUILD-INFO" "${dest}/BUILD-INFO"
( cd "${dest}" && sha256sum -c --quiet index.js.sha256 ) || die "post-install checksum mismatch at ${dest}"

# ---------------------------------------------------------------------------
log "3. Extract the image's externals (cross-checked against the hook this bundle patched)"
"${SCRIPT_DIR}/extract-externals.sh" --image "${image}" --storage-root "${storage_root}" --expect-hook-sha256 "${upstream_sha}"

log "DONE"
cat <<EOF
Installed: ${dest}/index.js (0644 root), externals under ${storage_root}/.externals/${runner_version}/
Selected by (second half of livespec-wm7c, ../arc/values-*.yaml + the provisioner setup seed):
  volumes:      hostPath ${dest} (Directory), mounted read-only in the runner container
  env:          ACTIONS_RUNNER_CONTAINER_HOOKS=<mount path>/index.js
                ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION=${runner_version}
  provisioner:  cp -al \${VOL_DIR%/*}/.externals/${runner_version}/. \${VOL_DIR}/externals
EOF
