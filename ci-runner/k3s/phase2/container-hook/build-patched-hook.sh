#!/usr/bin/env bash
# build-patched-hook.sh — reproducibly build the fleet-patched ARC Kubernetes
# container hook for the pinned runner image, proving on the way that the
# upstream version it patches is the one the image bundles.
#
# WHY A BUILD AT ALL: the pinned runner image ships the hook as a compiled ncc
# bundle (/home/runner/k8s/index.js, 8.9 MB) whose copyExternalsToRoot() copies
# /home/runner/externals (595 MB, 9,028 files, ~12 s) into the work volume on
# every job start, unconditionally (livespec-b1c6, verified 2026-09-04;
# livespec plan ci-runner-pod-lifecycle-reliability, research/005). The fleet
# runs a bundle that is upstream's bytes plus ONE patch (externals-skip.patch)
# skipping that copy when the platform pre-seeded the volume (livespec-wm7c).
# Hand-editing an 8.9 MB bundle would be unreviewable and unrepeatable, so the
# bundle is REBUILT from the upstream tag with the patch applied to the
# TypeScript source. Runs on a developer host, not the CI node: the output is
# committed under bundle/<runner-version>/ and install-container-hook.sh copies
# it from the checkout, so the node needs no Node toolchain.
#
# WHAT IT DOES, in order — every step fails loudly:
#   1. Resolve the runner image (--image, default the pin in
#      ../arc/values-livespec.yaml) and the runner version (its tag).
#   2. Derive the bundled hook version: `ARG RUNNER_CONTAINER_HOOKS_VERSION` in
#      actions/runner's images/Dockerfile at tag v<runner-version> — the only
#      place the image build takes it from (the publish workflow passes no
#      override; checked at v2.336.0 on 2026-09-04, where it reads 0.7.0).
#   3. Fetch upstream's release asset for that version
#      (actions-runner-hooks-k8s-<v>.zip -> index.js). When docker or podman is
#      on PATH, ALSO copy /home/runner/k8s/index.js out of the pinned image
#      (create + cp; the image is never run) and require the two byte-identical:
#      that ties the derived version to the bytes the pool runs, not to a
#      Dockerfile default. Without a runtime the check is recorded as skipped.
#   4. Clone actions/runner-container-hooks at v<hook-version>, build the
#      UNPATCHED bundle with the pinned Node, and require it byte-identical to
#      the release asset. Both Node 20 and 22 reproduce v0.7.0 exactly
#      (2026-09-04). If the toolchain cannot reproduce upstream's bytes, a
#      patched build is not "upstream plus the patch" and must not ship.
#   5. `git apply --check` externals-skip.patch — a runner-image bump that moves
#      the hook to a tag the patch no longer fits fails HERE, the intended block
#      (README.md "Runner-image bump") — then apply, rebuild, and require the
#      patched bundle to still carry copyExternalsToRoot, to now carry the env
#      and marker check, and to differ from the unpatched bundle by a bounded
#      number of lines.
#   6. Write <out-dir>/{index.js,index.js.sha256,BUILD-INFO}; BUILD-INFO records
#      every input so the artifact is auditable without re-running this.
#
# Requires: bash, git, curl, unzip, sha256sum, diff; Node via mise
# (`mise x node@$NODE_VERSION`) when mise is on PATH, else a `node` on PATH of
# the same major version. Network: GitHub (source, release asset, Dockerfile)
# and the npm registry. Nothing is installed outside the build directory.
#
# Usage: build-patched-hook.sh [--image <ref>] [--out-dir <dir>] [--keep-build-dir]
#   --image      runner image reference (tag@digest); default: the values pin
#   --out-dir    default <this dir>/bundle/<runner-version>
#   --keep-build-dir   keep the temporary build directory (printed) for inspection
# Env: NODE_VERSION (default 20.19.5), MAX_PATCH_DELTA_LINES (default 80).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CONTAINER_HOOK_DIR="${SCRIPT_DIR}"
# shellcheck source=./runner-image.sh
source "${SCRIPT_DIR}/runner-image.sh"

NODE_VERSION="${NODE_VERSION:-20.19.5}"
MAX_PATCH_DELTA_LINES="${MAX_PATCH_DELTA_LINES:-80}"
UPSTREAM_REPO="https://github.com/actions/runner-container-hooks.git"
UPSTREAM_RELEASES="https://github.com/actions/runner-container-hooks/releases/download"
RUNNER_DOCKERFILE_RAW="https://raw.githubusercontent.com/actions/runner"
PATCH="${SCRIPT_DIR}/externals-skip.patch"

USAGE="usage: build-patched-hook.sh [--image <ref>] [--out-dir <dir>] [--keep-build-dir]"
image=""
out_dir=""
keep_build=0
while [ $# -gt 0 ]; do
  case "$1" in
    --image) image="${2:?--image needs a value}"; shift 2 ;;
    --out-dir) out_dir="${2:?--out-dir needs a value}"; shift 2 ;;
    --keep-build-dir) keep_build=1; shift ;;
    -h|--help) echo "${USAGE}"; exit 0 ;;
    *) echo "FATAL: unknown argument '$1'"; echo "${USAGE}" >&2; exit 1 ;;
  esac
done

log() { printf '\n== %s ==\n' "$*"; }
die() { echo "FATAL: $*" >&2; exit 1; }

for t in git curl unzip sha256sum diff cmp; do
  command -v "$t" >/dev/null || die "$t not on PATH"
done
[ -f "${PATCH}" ] || die "patch file missing: ${PATCH}"

# Run a command with the pinned Node on PATH.
node_run() {
  if command -v mise >/dev/null; then
    mise x "node@${NODE_VERSION}" -- "$@"
  else
    "$@"
  fi
}
node_actual="$(node_run node --version 2>/dev/null || true)"
[ -n "${node_actual}" ] || die "no Node available: install mise (preferred) or put node ${NODE_VERSION%%.*}.x on PATH"
if [ "${node_actual%%.*}" != "v${NODE_VERSION%%.*}" ]; then
  die "Node major mismatch: want ${NODE_VERSION} (major ${NODE_VERSION%%.*}), have ${node_actual}"
fi
npm_actual="$(node_run npm --version)"

# ---------------------------------------------------------------------------
log "1. Resolve the pinned runner image"
image="$(resolve_runner_image "${image}")"
runner_version="$(runner_version_from_ref "${image}")"
digest_ref="$(digest_ref_from_ref "${image}")"
echo "image:          ${image}"
echo "runner version: ${runner_version}"
out_dir="${out_dir:-${SCRIPT_DIR}/bundle/${runner_version}}"

build="$(mktemp -d -t container-hook-build.XXXXXX)"
if [ "${keep_build}" -eq 1 ]; then
  echo "build dir (kept): ${build}"
else
  trap 'rm -rf "${build}"' EXIT
fi

# ---------------------------------------------------------------------------
log "2. Derive the bundled hook version from actions/runner v${runner_version} images/Dockerfile"
dockerfile_url="${RUNNER_DOCKERFILE_RAW}/v${runner_version}/images/Dockerfile"
curl -fsSL --retry 5 --retry-delay 3 -o "${build}/Dockerfile" "${dockerfile_url}" \
  || die "cannot fetch ${dockerfile_url} (is v${runner_version} a real actions/runner tag?)"
hook_version="$(sed -n -E 's/^ARG RUNNER_CONTAINER_HOOKS_VERSION=([0-9]+\.[0-9]+\.[0-9]+)[[:space:]]*$/\1/p' "${build}/Dockerfile" | head -1)"
[ -n "${hook_version}" ] || die "no 'ARG RUNNER_CONTAINER_HOOKS_VERSION=<x.y.z>' line in ${dockerfile_url}"
echo "hook version:   ${hook_version}  (from ${dockerfile_url})"

# ---------------------------------------------------------------------------
log "3. Fetch upstream's release asset for v${hook_version} and tie it to the image"
asset_url="${UPSTREAM_RELEASES}/v${hook_version}/actions-runner-hooks-k8s-${hook_version}.zip"
curl -fsSL --retry 5 --retry-delay 3 -o "${build}/release.zip" "${asset_url}" || die "cannot fetch ${asset_url}"
mkdir -p "${build}/release"
unzip -q -o "${build}/release.zip" -d "${build}/release"
[ -f "${build}/release/index.js" ] || die "release asset carries no index.js"
release_sha="$(sha256sum "${build}/release/index.js" | cut -d' ' -f1)"
echo "release index.js sha256: ${release_sha}"

runtime=""
for r in docker podman; do
  if command -v "$r" >/dev/null; then runtime="$r"; break; fi
done
if [ -n "${runtime}" ]; then
  echo "extracting /home/runner/k8s/index.js from the image with ${runtime} (create + cp; never run)"
  cid="$("${runtime}" create "${image}")" || die "${runtime} create ${image} failed"
  "${runtime}" cp "${cid}:/home/runner/k8s/index.js" "${build}/image-index.js" || die "${runtime} cp failed"
  "${runtime}" rm "${cid}" >/dev/null
  cmp -s "${build}/image-index.js" "${build}/release/index.js" \
    || die "the image's /home/runner/k8s/index.js is NOT the v${hook_version} release asset — the Dockerfile default was overridden at image build; derive the version another way"
  image_hook_check="byte-identical to the image's /home/runner/k8s/index.js (via ${runtime})"
else
  image_hook_check="skipped: no docker/podman on PATH (Dockerfile derivation only)"
fi
echo "image check:    ${image_hook_check}"

# ---------------------------------------------------------------------------
log "4. Clone v${hook_version} and reproduce the UNPATCHED bundle with Node ${node_actual}"
git -c advice.detachedHead=false clone --quiet --depth 1 --branch "v${hook_version}" "${UPSTREAM_REPO}" "${build}/src" \
  || die "cannot clone ${UPSTREAM_REPO} at tag v${hook_version}"
tag_commit="$(git -C "${build}/src" rev-parse HEAD)"
echo "tag commit:     ${tag_commit}"

build_bundle() {
  (
    cd "${build}/src"
    node_run bash -c '
      set -euo pipefail
      npm ci --prefix packages/hooklib --no-audit --no-fund --loglevel=error
      npm run --prefix packages/hooklib build >/dev/null
      npm ci --prefix packages/k8s --no-audit --no-fund --loglevel=error
      npm run --prefix packages/k8s build >/dev/null
    '
  )
}
build_bundle
cp "${build}/src/packages/k8s/dist/index.js" "${build}/unpatched-index.js"
unpatched_sha="$(sha256sum "${build}/unpatched-index.js" | cut -d' ' -f1)"
echo "unpatched build sha256:  ${unpatched_sha}"
cmp -s "${build}/unpatched-index.js" "${build}/release/index.js" \
  || die "the unpatched rebuild does not reproduce the v${hook_version} release bytes (toolchain drift: Node ${node_actual}, npm ${npm_actual}); refusing to ship a bundle that is not upstream-plus-patch"
echo "reproducible:   unpatched rebuild == release asset"

# ---------------------------------------------------------------------------
log "5. Apply externals-skip.patch and build the PATCHED bundle"
git -C "${build}/src" apply --check "${PATCH}" \
  || die "externals-skip.patch does not apply to v${hook_version}: re-derive the patch against that tag before this runner-image bump can ship (README.md \"Runner-image bump\")"
git -C "${build}/src" apply "${PATCH}"
build_bundle
cp "${build}/src/packages/k8s/dist/index.js" "${build}/patched-index.js"
patched="${build}/patched-index.js"
grep -q 'function copyExternalsToRoot' "${patched}" || die "patched bundle lost copyExternalsToRoot (upstream prepareJob path)"
grep -q 'ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION' "${patched}" || die "patched bundle carries no ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION check"
grep -q 'externals-seeded-' "${patched}" || die "patched bundle carries no .externals-seeded-<version> marker check"
delta="$(diff "${build}/unpatched-index.js" "${patched}" | grep -c '^[<>]' || true)"
[ "${delta}" -gt 0 ] || die "patched bundle is byte-identical to the unpatched one"
[ "${delta}" -le "${MAX_PATCH_DELTA_LINES}" ] || die "patched bundle differs from the unpatched one by ${delta} lines (> ${MAX_PATCH_DELTA_LINES}); the patch did more than intended"
patched_sha="$(sha256sum "${patched}" | cut -d' ' -f1)"
patched_bytes="$(wc -c < "${patched}")"
echo "patched build sha256:    ${patched_sha}  (${patched_bytes} bytes, ${delta} lines differ from upstream)"

# ---------------------------------------------------------------------------
log "6. Write ${out_dir}"
install -d -m 0755 "${out_dir}"
cp "${patched}" "${out_dir}/index.js"
chmod 0644 "${out_dir}/index.js"
( cd "${out_dir}" && sha256sum index.js > index.js.sha256 )
cat > "${out_dir}/BUILD-INFO" <<EOF
runner_image=${image}
runner_image_digest_ref=${digest_ref}
runner_version=${runner_version}
hook_version=${hook_version}
hook_version_source=${dockerfile_url}
hook_tag_commit=${tag_commit}
upstream_release_asset=${asset_url}
upstream_index_js_sha256=${release_sha}
image_hook_check=${image_hook_check}
unpatched_rebuild_sha256=${unpatched_sha}
patch_file=externals-skip.patch
patch_sha256=$(sha256sum "${PATCH}" | cut -d' ' -f1)
patched_index_js_sha256=${patched_sha}
patched_index_js_bytes=${patched_bytes}
patch_delta_lines=${delta}
node_version=${node_actual}
npm_version=${npm_actual}
built_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
EOF
cat "${out_dir}/BUILD-INFO"
log "DONE: ${out_dir}/index.js (sha256 ${patched_sha})"
