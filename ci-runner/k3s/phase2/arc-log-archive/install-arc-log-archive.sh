#!/usr/bin/env bash
# install-arc-log-archive.sh — install the ARC log archive on a k3s runner NODE:
# the archive script into /usr/local/lib, then the oneshot service and its
# 2-minute timer into /etc/systemd/system.
#
# WHY A SCRIPT rather than three hand-run `install` commands: the same reasoning
# as the sibling ../wedged-runner/install-wedged-runner-scan.sh. The unit's
# ExecStart path (/usr/local/lib/ci-runner-k3s/archive-arc-logs.sh) is a COPY of
# a script living in this repository, so installing the unit without copying the
# script yields a timer that fires every two minutes and fails every time.
#
# NODE-LOCAL, like its siblings: systemd units are machine state. Re-run on any
# node added to the pool and after any node rebuild.
#
# NO MODE ARGUMENT, deliberately, and the contrast with the sibling installer is
# the point. `install-wedged-runner-scan.sh` requires report-vs-clear because
# that choice decides whether the sweep DELETES pods, and a default would be
# making a destructive decision on the operator's behalf. This one only ever
# appends to files under /var/log; there is no destructive variant to choose
# between, so an argument would be ceremony rather than a safeguard.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="archive-arc-logs.service"
TIMER="archive-arc-logs.timer"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install the archive script to ${LIB_DIR} (the unit's ExecStart path)"
install -d -m 0755 "${LIB_DIR}"
install -m 0755 "${SCRIPT_DIR}/archive-arc-logs.sh" "${LIB_DIR}/archive-arc-logs.sh"

# ---------------------------------------------------------------------------
log "2. Create the archive and state directories"
# 0750 rather than 0755: ARC logs carry installation ids, session uuids, and
# repository names. None of that is a credential, but none of it needs to be
# world-readable on a host that also runs job containers.
install -d -m 0750 /var/log/arc-archive
install -d -m 0750 /var/lib/ci-runner-k3s/arc-log-archive

# ---------------------------------------------------------------------------
log "3. Install the unit files"
install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"

# ---------------------------------------------------------------------------
log "4. Enable and start the timer"
systemctl daemon-reload
systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "5. Verify: run one archive pass now and show its output"
systemctl start "${SERVICE}" || true
systemctl --no-pager status "${TIMER}" || true
journalctl -u "${SERVICE}" -n 30 --no-pager || true

log "DONE. ${TIMER} armed; ARC logs archived to /var/log/arc-archive every 2 minutes."
