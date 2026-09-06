#!/usr/bin/env bash
# extract-externals.sh — NODE-LOCAL (root): put a host copy of the pinned
# runner image's /home/runner/externals where the local-path provisioner's
# setup script can hardlink-seed every runner work volume from it, with the
# marker file the fleet-patched container hook checks before it skips its copy.
#
# WHY: the hook copies those 595 MB / 9,028 files into the work volume on every
# job start (~12 s; livespec-b1c6, research/005 of livespec plan
# ci-runner-pod-lifecycle-reliability). A hardlink seed at volume provisioning
# costs metadata writes only, but link(2) needs source and destination on ONE
# filesystem — so the copy lives under the local-path storage root, on the
# ci-workvols tier (../README.md "Storage layout"), as a hidden sibling of the
# pvc-* directories: <storage-root>/.externals/<runner-version>/. That is the
# same convention as the warm-cache seed root (.warm, livespec-lvtu), and the
# boot-time storage sweep (../storage-sweep/) removes only pvc-* names, so the
# copy survives it. The seed itself is the provisioner setup script's job
# (second half of livespec-wm7c, after livespec-lvtu lands): `cp -al` of this
# directory to ${VOL_DIR}/externals, marker included.
#
# HOW: mount the image READ-ONLY with containerd's ctr (k3s's ctr symlink, or
# `k3s ctr`; the image is never run), pulling it first only if this node has
# never run a runner pod (what the kubelet would do anyway); cross-check the
# runner version inside it (bin/Runner.Listener.deps.json names it — the image
# carries no version label or env); optionally cross-check the bundled hook's
# sha256 against what the patched hook was built from (--expect-hook-sha256,
# passed by install-container-hook.sh); `cp -a` the tree into a staging
# directory beside the destination; write the marker; verify a per-file sha256
# manifest of the copy against one taken from the source; move it into place;
# record the manifest OUTSIDE the seeded tree (<dest>.MANIFEST.sha256) so it is
# never hardlinked into a volume. Ownership and modes are the image's (runner
# 1001:123, 0644/0755), exactly what the kubelet's own image layer presents.
#
# IDEMPOTENT: a re-run whose source manifest equals the recorded one changes
# nothing and says so. A changed image (a bump) lands under its own version
# directory; the previous version's directory is left for the operator to
# remove once no values file names it (hardlinks in live volumes keep their
# inodes regardless).
#
# The marker: <dest>/.externals-seeded-<runner-version>, content the runner
# version. externals-skip.patch skips the copy only when the runner's
# ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION names that same version.
#
# Usage: extract-externals.sh [--image <ref>] [--storage-root <dir>]
#                             [--expect-hook-sha256 <sha256>] [--dry-run]
#   --image        runner image reference (tag@digest); default: the values pin
#   --storage-root default /var/lib/rancher/k3s/storage (the local-path root)
#   --expect-hook-sha256  fail unless the image's /home/runner/k8s/index.js
#                  has this sha256 (the upstream_index_js_sha256 of BUILD-INFO)
#   --dry-run      resolve and print the plan; touch nothing; needs no root
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export CONTAINER_HOOK_DIR="${SCRIPT_DIR}"
# shellcheck source=./runner-image.sh
source "${SCRIPT_DIR}/runner-image.sh"

CTR_NAMESPACE="k8s.io"
USAGE="usage: extract-externals.sh [--image <ref>] [--storage-root <dir>] [--expect-hook-sha256 <sha256>] [--dry-run]"
image=""
storage_root="/var/lib/rancher/k3s/storage"
expect_hook_sha=""
dry_run=0
while [ $# -gt 0 ]; do
  case "$1" in
    --image) image="${2:?--image needs a value}"; shift 2 ;;
    --storage-root) storage_root="${2:?--storage-root needs a value}"; shift 2 ;;
    --expect-hook-sha256) expect_hook_sha="${2:?--expect-hook-sha256 needs a value}"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) echo "${USAGE}"; exit 0 ;;
    *) echo "FATAL: unknown argument '$1'" >&2; echo "${USAGE}" >&2; exit 1 ;;
  esac
done

log() { printf '\n== %s ==\n' "$*"; }
die() { echo "FATAL: $*" >&2; exit 1; }

image="$(resolve_runner_image "${image}")"
runner_version="$(runner_version_from_ref "${image}")"
digest_ref="$(digest_ref_from_ref "${image}")"
externals_root="${storage_root}/.externals"
dest="${externals_root}/${runner_version}"
manifest="${externals_root}/${runner_version}.MANIFEST.sha256"
marker=".externals-seeded-${runner_version}"
if [ -n "${expect_hook_sha}" ] && ! [[ "${expect_hook_sha}" =~ ^[0-9a-f]{64}$ ]]; then
  die "--expect-hook-sha256 is not a hex sha256: '${expect_hook_sha}'"
fi

# containerd's ctr: k3s installs a `ctr` symlink pointed at its own socket; the
# `k3s ctr` subcommand is the same thing when the symlink is absent.
if command -v ctr >/dev/null; then
  CTR=(ctr)
elif command -v k3s >/dev/null; then
  CTR=(k3s ctr)
else
  CTR=()
fi

echo "image:          ${image}"
echo "digest ref:     ${digest_ref}"
echo "runner version: ${runner_version}"
echo "destination:    ${dest}"
echo "manifest:       ${manifest}"
echo "marker:         ${dest}/${marker}  (content: ${runner_version})"
echo "hook check:     ${expect_hook_sha:-none requested}"

if [ "${dry_run}" -eq 1 ]; then
  log "DRY RUN — nothing touched. The run would:"
  echo "  1. ${CTR[*]:-ctr} -n ${CTR_NAMESPACE} images ls -q            (pull ${digest_ref} if absent)"
  echo "  2. ${CTR[*]:-ctr} -n ${CTR_NAMESPACE} images mount --rw=false ${digest_ref} <tmp mountpoint>"
  echo "  3. verify Runner.Listener/${runner_version} in <mount>/home/runner/bin/Runner.Listener.deps.json"
  [ -n "${expect_hook_sha}" ] && echo "  3b. verify sha256(<mount>/home/runner/k8s/index.js) == ${expect_hook_sha}"
  echo "  4. manifest <mount>/home/runner/externals; no-op if it equals ${manifest}"
  echo "  5. cp -a into ${externals_root}/.tmp-${runner_version}.<pid>, write ${marker}, verify, mv to ${dest}"
  echo "  6. ${CTR[*]:-ctr} -n ${CTR_NAMESPACE} images unmount <tmp mountpoint>"
  exit 0
fi

[ "$(id -u)" -eq 0 ] || die "must run as root (mounts the image, writes ${externals_root})"
[ "${#CTR[@]}" -gt 0 ] || die "neither ctr nor k3s on PATH"
for t in sha256sum find sort cmp cp mv; do command -v "$t" >/dev/null || die "$t not on PATH"; done
[ -d "${storage_root}" ] || die "storage root ${storage_root} does not exist (is the ci-workvols bind mounted?)"

# The tree's identity: every regular file's sha256 plus every symlink's target,
# in a stable order. Taken from the mount and from the copy; the two must agree.
manifest_of() {
  ( cd "$1" && {
      find . -type f -print0 | sort -z | xargs -0 --no-run-if-empty sha256sum
      find . -type l -printf '%p -> %l\n' | sort
    } )
}

# ---------------------------------------------------------------------------
log "1. Image present in containerd (${CTR_NAMESPACE})?"
present="$("${CTR[@]}" -n "${CTR_NAMESPACE}" images ls -q 2>/dev/null | grep -Fx -e "${digest_ref}" -e "${image%%@*}" || true)"
if [ -z "${present}" ]; then
  echo "not present; pulling ${digest_ref} (what the kubelet does before the first runner pod)"
  "${CTR[@]}" -n "${CTR_NAMESPACE}" images pull "${digest_ref}" >/dev/null || die "ctr pull ${digest_ref} failed"
  mount_ref="${digest_ref}"
else
  mount_ref="$(printf '%s\n' "${present}" | head -1)"
  echo "present as ${mount_ref}"
fi

# ---------------------------------------------------------------------------
log "2. Mount the image read-only"
mnt="$(mktemp -d -t runner-image.XXXXXX)"
staging="${externals_root}/.tmp-${runner_version}.$$"
cleanup() {
  "${CTR[@]}" -n "${CTR_NAMESPACE}" images unmount "${mnt}" >/dev/null 2>&1 || true
  rmdir "${mnt}" 2>/dev/null || true
  rm -rf "${staging}"
}
trap cleanup EXIT
"${CTR[@]}" -n "${CTR_NAMESPACE}" images mount --rw=false "${mount_ref}" "${mnt}" >/dev/null || die "ctr images mount ${mount_ref} failed"
src="${mnt}/home/runner/externals"
[ -d "${src}" ] || die "${src} missing in the mounted image"

# ---------------------------------------------------------------------------
log "3. Cross-check the runner inside the image"
deps="${mnt}/home/runner/bin/Runner.Listener.deps.json"
[ -f "${deps}" ] || die "${deps} missing — not a runner image?"
inside="$(grep -o '"Runner.Listener/[0-9][0-9.]*"' "${deps}" | head -1 | sed 's/.*\///; s/"//')"
[ "${inside}" = "${runner_version}" ] || die "image tag says runner ${runner_version} but the image carries Runner.Listener/${inside}"
echo "Runner.Listener/${inside} matches the tag"
if [ -n "${expect_hook_sha}" ]; then
  actual_hook_sha="$(sha256sum "${mnt}/home/runner/k8s/index.js" | cut -d' ' -f1)"
  [ "${actual_hook_sha}" = "${expect_hook_sha}" ] \
    || die "the image's /home/runner/k8s/index.js sha256 is ${actual_hook_sha}, not the ${expect_hook_sha} the patched hook was built from — rebuild the hook for this image"
  echo "bundled hook sha256 ${actual_hook_sha} matches the build's upstream input"
fi

# ---------------------------------------------------------------------------
log "4. Manifest the source; no-op if already extracted byte-for-byte"
manifest_of "${src}" > "${mnt%/*}/$(basename "${mnt}").source-manifest"
source_manifest="${mnt%/*}/$(basename "${mnt}").source-manifest"
trap 'cleanup; rm -f "${source_manifest}"' EXIT
file_count="$(grep -c '^[0-9a-f]\{64\}  ' "${source_manifest}" || true)"
echo "source: ${file_count} regular files, $(du -sm "${src}" | cut -f1) MB"
if [ -f "${manifest}" ] && [ -f "${dest}/${marker}" ] && cmp -s "${manifest}" "${source_manifest}" \
   && [ "$(cat "${dest}/${marker}")" = "${runner_version}" ]; then
  log "DONE: ${dest} already holds this image's externals byte-for-byte (manifest ${manifest} unchanged); nothing to do"
  exit 0
fi

# ---------------------------------------------------------------------------
log "5. Copy into staging, mark, verify, move into place"
install -d -m 0755 "${externals_root}"
rm -rf "${externals_root}"/.tmp-"${runner_version}".* 2>/dev/null || true
mkdir -m 0755 "${staging}"
cp -a "${src}/." "${staging}/"
printf '%s\n' "${runner_version}" > "${staging}/${marker}"
chmod 0644 "${staging}/${marker}"
# Verify the copy against the source (the marker is ours, not the image's, so
# it is excluded from the comparison).
manifest_of "${staging}" | grep -v -- " ./${marker}\$" > "${staging}.manifest"
cmp -s "${staging}.manifest" "${source_manifest}" || { rm -f "${staging}.manifest"; die "the copy under ${staging} does not match the source manifest"; }
if [ -e "${dest}" ]; then
  old="${externals_root}/.replaced-${runner_version}.$(date -u +%Y%m%dT%H%M%SZ)"
  echo "replacing the existing ${dest} (moved to ${old}, then removed; live hardlinks keep their inodes)"
  mv "${dest}" "${old}"
  rm -rf "${old}"
fi
mv "${staging}" "${dest}"
mv "${staging}.manifest" "${manifest}"
chmod 0644 "${manifest}"
log "DONE: ${dest} (${file_count} files, marker ${marker}); manifest ${manifest}"
