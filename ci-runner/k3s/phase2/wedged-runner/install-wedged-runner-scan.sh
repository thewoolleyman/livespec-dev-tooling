#!/usr/bin/env bash
# install-wedged-runner-scan.sh — install the wedged-runner sweep on a k3s
# runner NODE: the scan script into /usr/local/lib, then the oneshot service
# and its 5-minute timer into /etc/systemd/system, with MODE_PLACEHOLDER
# substituted for the chosen mode.
#
# WHY A SCRIPT rather than three hand-run `install` commands: exactly the
# reasoning in the sibling ../node-extended-resource/install-reapply-unit.sh —
# the shipped unit is deliberately not runnable as-is (its ExecStart says
# MODE_PLACEHOLDER), which makes installation a substitution step, and a
# substitution step done by hand is a step that gets done differently twice. It
# also encodes the dependency the unit file cannot state: the ExecStart path
# /usr/local/lib/ci-runner-k3s/scan-wedged-runners.sh is a COPY of a script
# living in this repository, so installing the unit without copying the script
# yields a timer that fires every five minutes and fails every time.
#
# NODE-LOCAL, like install-reapply-unit.sh and ../apparmor/install-apparmor-profile.sh:
# systemd units are machine state. Re-run on any node added to the pool and
# after any node rebuild.
#
# MODE IS REQUIRED AND NOT DEFAULTED, and the reason is a real decision rather
# than caution-by-habit:
#
#   report  — the sweep prints findings and exits non-zero, so the unit lands in
#             `failed` and `systemctl is-failed scan-wedged-runners.service`
#             becomes the signal. Correct wherever something actually watches
#             unit state.
#
#   clear   — the sweep additionally DELETES flagged pods.
#
# `clear` is the mode installed on poweredge-xubuntu (2026-08-19,
# livespec-s43svm.30), and the argument for it is that report-only is not a
# weaker remedy on this host, it is no remedy: nothing on poweredge-xubuntu
# routes systemd unit failures anywhere a human sees them, so a report-only
# sweep reproduces the exact recovery path that already failed — a wedge
# sitting until somebody happens to look. Against that, the deletion is safe by
# construction and guarded three ways: scale-set runner pods are ephemeral and
# ARC replaces a deleted one within seconds; a flagged pod is by definition
# incapable of holding work; and the scan refuses to delete any pod with a live
# `-workflow` companion, which is the one observable that could distinguish a
# false positive. See scan-wedged-runners.sh's header for the full argument.
#
# A host that DOES watch unit state should prefer `report`, so the delete stays
# an operator action. The mode is an argument rather than a repo-wide constant
# precisely because that answer is per host.
#
# Requires: root, systemd, and the same KUBECONFIG the service itself uses.
set -euo pipefail

USAGE="usage: install-wedged-runner-scan.sh MODE   (MODE is 'report' or 'clear' -- see this script's header)"
MODE="${1:?$USAGE}"

case "$MODE" in
  report) MODE_ARG="" ;;
  clear)  MODE_ARG="--clear" ;;
  *)      echo "FATAL: MODE must be 'report' or 'clear', got '${MODE}'" >&2; exit 1 ;;
esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="scan-wedged-runners.service"
TIMER="scan-wedged-runners.timer"

log() { printf '\n== %s ==\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root (writes /usr/local/lib and /etc/systemd/system)"; exit 1; }
command -v systemctl >/dev/null || { echo "FATAL: systemctl not found on PATH"; exit 1; }

# ---------------------------------------------------------------------------
log "1. Install the scan script to ${LIB_DIR} (the unit's ExecStart path)"
install -d -m 0755 "${LIB_DIR}"
install -m 0755 "${SCRIPT_DIR}/scan-wedged-runners.sh" "${LIB_DIR}/scan-wedged-runners.sh"

# ---------------------------------------------------------------------------
log "2. Install the unit files, substituting mode=${MODE}"
sed "s|MODE_PLACEHOLDER|${MODE_ARG}|" "${SCRIPT_DIR}/${SERVICE}" > "${UNIT_DIR}/${SERVICE}"
chmod 0644 "${UNIT_DIR}/${SERVICE}"
install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"

# Fail loudly rather than installing a unit that would fail every five minutes.
if grep -q MODE_PLACEHOLDER "${UNIT_DIR}/${SERVICE}"; then
  echo "FATAL: MODE_PLACEHOLDER survived substitution in ${UNIT_DIR}/${SERVICE}"
  exit 1
fi

# ---------------------------------------------------------------------------
log "3. Enable and start the timer"
systemctl daemon-reload
systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "4. Verify: run the sweep once now and show its output"
# `|| true` because in report mode a genuine finding EXITS NON-ZERO by design,
# and an installer that aborts on a true positive would be reporting the
# install as broken when it is in fact working.
systemctl start "${SERVICE}" || true
systemctl --no-pager status "${TIMER}" || true
journalctl -u "${SERVICE}" -n 40 --no-pager || true

log "DONE. ${TIMER} armed; ${SERVICE} sweeps for wedged runners every 5 minutes in '${MODE}' mode."
