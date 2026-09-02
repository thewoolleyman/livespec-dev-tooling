#!/usr/bin/env bash
# install-runner-pod-lifecycle-scan.sh — install the runner-pod lifecycle
# sweep on a k3s runner NODE: the scan script into /usr/local/lib, then the
# oneshot service and its 5-minute timer into /etc/systemd/system, enabled
# and started.
#
# WHY A SCRIPT rather than three hand-run `install` commands: the same
# reasoning as ../wedged-runner/install-wedged-runner-scan.sh — the unit's
# ExecStart names /usr/local/lib/ci-runner-k3s/scan-runner-pod-lifecycle.sh,
# a COPY of a script living in this repository, so installing the unit
# without copying the script yields a timer that fires every five minutes and
# fails every time; and the copy plus the two unit files done by hand is a
# step that gets done differently twice.
#
# NO MODE ARGUMENT, unlike the wedged-runner installer, and the absence is a
# decision rather than an omission: this sweep has no --clear. Nothing in the
# lifecycle-stall family is safe to delete automatically (a Pending PVC is a
# claim a runner is waiting on; a Pending workflow pod is a job in flight; a
# StartError'd pod is evidence; the stale-listener delete is a scale-set-level
# action an operator should take knowingly), so there is no choice for the
# operator to make at install time and the shipped unit is runnable as-is.
# The scan's report mode is the whole interface: exit 1 with the classes
# named, so `systemctl is-failed scan-runner-pod-lifecycle.service` and the
# journal carry the signal. See scan-runner-pod-lifecycle.sh's header.
#
# NODE-LOCAL, like every installer in this tree: systemd units and
# /usr/local/lib copies are machine state. Re-run on any node added to the
# pool and after any node rebuild.
#
# Requires: root, systemd, and the same KUBECONFIG the service itself uses.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="scan-runner-pod-lifecycle.service"
TIMER="scan-runner-pod-lifecycle.timer"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)" >&2; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH" >&2; exit 1; }
for f in scan-runner-pod-lifecycle.sh "$SERVICE" "$TIMER"; do
  [ -f "${SCRIPT_DIR}/${f}" ] || { echo "FATAL: ${SCRIPT_DIR}/${f} not found" >&2; exit 1; }
done

# ---------------------------------------------------------------------------
log "1. Copy the scan script to ${LIB_DIR}"
install -d -m 0755 "${LIB_DIR}"
install -m 0755 "${SCRIPT_DIR}/scan-runner-pod-lifecycle.sh" "${LIB_DIR}/scan-runner-pod-lifecycle.sh"

# ---------------------------------------------------------------------------
log "2. Install the service and timer"
install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"
systemctl daemon-reload

# ---------------------------------------------------------------------------
log "3. Enable and start the timer"
systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "4. Verify"
state="$(systemctl is-active "${TIMER}" 2>/dev/null || true)"
[ "$state" = "active" ] || { echo "FATAL: ${TIMER} is '${state}', expected 'active'" >&2; exit 1; }
systemctl list-timers --no-pager --all "${TIMER}" | head -3

log "DONE. ${TIMER} active; the sweep runs every 5 minutes in report mode."
log "Read findings with: journalctl -u ${SERVICE} -n 60 --no-pager; check state with: systemctl is-failed ${SERVICE}"
