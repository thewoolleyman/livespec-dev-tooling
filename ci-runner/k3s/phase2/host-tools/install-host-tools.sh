#!/usr/bin/env bash
# install-host-tools.sh — install the operator-facing host tools this tree
# carries into /usr/local/bin on a k3s runner NODE. Idempotent: `install`
# overwrites byte-for-byte and never touches anything it does not own.
#
# WHY THIS EXISTS: on 2026-09-06 `btop-loop` was written straight to
# /usr/local/bin on poweredge-xubuntu at the maintainer's request, which made
# it the one host change of that day with no repository realization. The
# maintainer's rule is that everything on the CI host is in gitops and
# rebuildable from scratch, so the tool lives here and install-node.sh
# (step 2d) installs it with every other node-local mechanism.
#
# TOOLS
#   btop-loop   run btop in the current terminal and restart it after an
#               abnormal exit. btop 1.4.6 aborts (SIGABRT) when one
#               collect-and-draw cycle exceeds its hard-coded 5 s stall
#               limit, which a CI fan-out with ~6,400 processes and hundreds
#               of veth interfaces reliably causes (upstream aristocratos/btop
#               issue #1746). Quit with q; Ctrl-C also stops the loop.
#
# NODE-LOCAL, like every sibling installer: /usr/local/bin is machine state.
# Re-run on any node added to the pool and after any node rebuild.
#
# Requires: root (writes /usr/local/bin).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="/usr/local/bin"

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes ${BIN_DIR})" >&2; exit 1; }

# The tools this tree installs. One element today; the loop is the shape the
# next one lands in, so adding a tool is a one-line change.
TOOLS=(btop-loop)

for tool in "${TOOLS[@]}"; do
    install -m 0755 "${SCRIPT_DIR}/${tool}" "${BIN_DIR}/${tool}"
    printf '== installed %s ==\n' "${BIN_DIR}/${tool}"
done
