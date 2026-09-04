#!/usr/bin/env bash
# install-cache-telemetry.sh — NODE-LOCAL: put the pool-provided cache-span
# emitter (./ci-cache-span.sh) at /usr/local/lib/ci-runner-k3s/bin/ci-cache-span,
# the directory ../arc/hook-pod-template.yaml mounts READ-ONLY into every job
# container at /opt/ci-runner/bin — the same placement as sccache
# (../sccache/install-sccache-binary.sh), for the same reason: no routed
# repository bumps its `container:` pin to get the tier's telemetry.
#
# Idempotent: exits 0 without writing when the installed file is byte-identical.
# Machine state, like the other node-local installers: install-node.sh runs
# it; re-run after changing ci-cache-span.sh (the ConfigMap converge does NOT
# carry it — it is a file on the node, not a cluster object).
#
# Requires: root (writes /usr/local/lib).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="/usr/local/lib/ci-runner-k3s/bin"
SRC="${SCRIPT_DIR}/ci-cache-span.sh"
DEST="${BIN_DIR}/ci-cache-span"
[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${BIN_DIR})"; exit 1; }
[ -f "${SRC}" ] || { echo "FATAL: ${SRC} missing"; exit 1; }
if [ -f "${DEST}" ] && cmp -s "${SRC}" "${DEST}"; then
  printf '\n== ci-cache-span already installed at %s ==\n' "${DEST}"
  exit 0
fi
install -o root -g root -m 0755 -d "${BIN_DIR}"
install -o root -g root -m 0755 "${SRC}" "${DEST}"
printf '\n== ci-cache-span installed at %s ==\n' "${DEST}"
