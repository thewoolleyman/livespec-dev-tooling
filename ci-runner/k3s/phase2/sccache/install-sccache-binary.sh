#!/usr/bin/env bash
# install-sccache-binary.sh — NODE-LOCAL: put the pinned, checksum-verified
# sccache binary at /usr/local/lib/ci-runner-k3s/bin/sccache, the directory
# ../arc/hook-pod-template.yaml mounts READ-ONLY into every job container (and
# ../warm-cache/warm-cache-cronjob.yaml into the populator) at
# /opt/ci-runner/bin. The pool PROVIDES sccache rather than baking it into the
# sandbox image so that (a) no routed repository has to bump its `container:`
# pin to get the tier — the transparency requirement — and (b) the binary
# every consumer runs is one file on the host, bumped in one place.
#
# Idempotent: exits 0 without downloading when the installed binary already
# reports the pinned version. Re-run after bumping the pin. Like the other
# node-local installers (../node-extended-resource/, ../reconstruct/), this is
# machine state: re-run on a node rebuild (install-node.sh does).
#
# Requires: root (writes /usr/local/lib), curl, tar, sha256sum.
set -euo pipefail

SCCACHE_VERSION="${SCCACHE_VERSION:-0.17.0}"
# sha256 of sccache-v${SCCACHE_VERSION}-x86_64-unknown-linux-musl.tar.gz, from
# the release's published .sha256 asset (read 2026-09-04). Bump with the version.
SCCACHE_SHA256="${SCCACHE_SHA256:-67c4a96dd237c1f518f6b36083f270f9976d516f1e57fce891755ea782e50006}"
BIN_DIR="/usr/local/lib/ci-runner-k3s/bin"
DEST="${BIN_DIR}/sccache"
ASSET="sccache-v${SCCACHE_VERSION}-x86_64-unknown-linux-musl"
URL="https://github.com/mozilla/sccache/releases/download/v${SCCACHE_VERSION}/${ASSET}.tar.gz"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${BIN_DIR})"; exit 1; }
for t in curl tar sha256sum; do command -v "$t" >/dev/null || { echo "FATAL: $t not on PATH"; exit 1; }; done

if [ -x "${DEST}" ] && "${DEST}" --version 2>/dev/null | grep -q "sccache ${SCCACHE_VERSION}\$"; then
  log "sccache ${SCCACHE_VERSION} already installed at ${DEST}"
  exit 0
fi

log "1. Download ${URL}"
tmp="$(mktemp -d)"
trap 'rm -rf "${tmp}"' EXIT
curl -fsSL --retry 5 --retry-all-errors --retry-delay 3 -o "${tmp}/${ASSET}.tar.gz" "${URL}"

log "2. Verify the checksum"
echo "${SCCACHE_SHA256}  ${tmp}/${ASSET}.tar.gz" | sha256sum -c -

log "3. Install ${DEST}"
tar -xzf "${tmp}/${ASSET}.tar.gz" -C "${tmp}" "${ASSET}/sccache"
install -d -m 0755 "${BIN_DIR}"
install -m 0755 "${tmp}/${ASSET}/sccache" "${DEST}"
"${DEST}" --version
log "DONE: ${DEST} ($("${DEST}" --version))"
