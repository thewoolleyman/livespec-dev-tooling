#!/usr/bin/env bash
# install-runner-pod-lifecycle-scan.sh — install the runner-pod lifecycle
# sweep on the k3s SERVER node: the scan script into /usr/local/lib, then the
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
# /usr/local/lib copies are machine state. Re-run after any SERVER node
# rebuild.
#
# SERVER-ONLY, AND IT NOW REFUSES ON AN AGENT (2026-09-07,
# livespec-dev-tooling-qcq0, livespec plan `k3s-on-gmktec-for-vps-usage` carrier
# R3). Run on gmktec-xubuntu — the fleet's first agent — this installer put both
# units on the host and then died at its own verify, correctly, because the
# service is server-shaped THREE ways and an agent satisfies none of them:
#
#   * it is ordered `After=`/`Requires=k3s.service`, and an agent runs
#     `k3s-agent.service`, so `systemctl start` fails with "Unit k3s.service not
#     found" and the timer lands `failed (Result: resources)` — which is what
#     took ../install-node.sh's whole runbook down at step 5b of 10, before five
#     later steps that had nothing to do with this one;
#   * it carries `Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml`, the admin
#     file only a server holds;
#   * scan-runner-pod-lifecycle.sh reads PVCs, scheduler events, scale-set
#     listeners and node capacity CLUSTER-WIDE — a pool-wide diagnosis rather
#     than a node-local one. The SERVER's own scan-runner-pod-lifecycle.timer
#     already performs exactly that sweep every five minutes and already covers
#     this node's pods.
#
# So installing this on an agent is wrong in KIND, not merely misconfigured. An
# agent invocation therefore REFUSES — and, because the pre-refusal run left
# both units on gmktec, it first REMOVES any copy it finds, so a re-run leaves a
# clean host instead of a dead timer.
#
# Requires: root, systemd, and the same KUBECONFIG the service itself uses.
# `--dry-run` requires none of them and executes nothing — it is what makes the
# role decision assertable off-host
# (./install-runner-pod-lifecycle-scan-exit-tests.sh).
#
# Usage: install-runner-pod-lifecycle-scan.sh [--dry-run] [--role server|agent]
#   --role    the node's cluster role. Defaults to the CLUSTER_ROLE environment
#             variable when set, and to `server` otherwise — which is what a
#             bare invocation meant before this script knew about roles.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="scan-runner-pod-lifecycle.service"
TIMER="scan-runner-pod-lifecycle.timer"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--role server|agent]   (--role defaults to \$CLUSTER_ROLE, then to server)"

AGENT_REFUSAL_REASON="${SERVICE} is SERVER-SHAPED and an agent satisfies none of it: Requires=k3s.service (an agent runs k3s-agent.service, so the unit cannot even start), Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml (the admin file only a server holds), and scan-runner-pod-lifecycle.sh reads PVCs, scheduler events, scale-set listeners and node capacity CLUSTER-WIDE -- a pool-wide diagnosis the SERVER's own ${TIMER} already performs every five minutes over every pod on every node, this one included."

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
ROLE=""
ROLE_GIVEN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --role)
      [ $# -ge 2 ] || die "--role needs a value -- ${USAGE}"
      [ -n "$2" ] || die "--role needs a value -- ${USAGE}"
      [ "$ROLE_GIVEN" -eq 0 ] || die "--role given more than once -- ${USAGE}"
      ROLE_GIVEN=1
      ROLE="$2"; shift ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *) die "unexpected argument '$1' -- ${USAGE}" ;;
  esac
  shift
done

ROLE="${ROLE:-${CLUSTER_ROLE:-server}}"
case "$ROLE" in
  server|agent) ;;
  *) die "role must be 'server' or 'agent', got '${ROLE}'" ;;
esac

# ---------------------------------------------------------------------------
# ONE call site per command, printed as a '+ ' line and executed unless this is
# a dry run, so the sequence a dry run prints cannot describe a different run
# from the one that happens.
# ---------------------------------------------------------------------------
run() {  # run CMD ARG...
  printf '+ %s\n' "$*"
  [ "$DRY_RUN" -eq 1 ] || "$@"
}

# READ, not a mutation, so it is performed even under --dry-run: the removal
# sequence a dry run prints has to be the one this host actually needs. Two
# probes because either alone is incomplete — a unit file can be on disk while
# systemd has never been told about it, and `systemctl disable` leaves the file
# in place.
unit_installed() {  # unit_installed NAME
  if [ -e "${UNIT_DIR}/$1" ]; then
    return 0
  fi
  if ! command -v systemctl >/dev/null 2>&1; then
    return 1
  fi
  [ -n "$(systemctl list-unit-files --no-legend "$1" 2>/dev/null)" ]
}

# The timer BEFORE the service it triggers, so nothing fires between the two.
remove_installed_units() {
  local unit removed=0
  for unit in "$TIMER" "$SERVICE"; do
    if unit_installed "$unit"; then
      removed=1
      # A failed `disable` does not stop the removal: the unit this cleans up
      # after is one systemd could not start in the first place, and deleting
      # the file is the half that actually clears it. Reported, never silent.
      run systemctl disable --now "$unit" \
        || printf '  disable failed for %s -- removing the unit file anyway\n' "$unit"
      run rm -f "${UNIT_DIR}/${unit}"
    fi
  done
  if [ "$removed" -eq 1 ]; then
    run systemctl daemon-reload
  else
    printf '  nothing to remove: neither %s nor %s is installed on this node\n' "$SERVICE" "$TIMER"
  fi
}

# ---------------------------------------------------------------------------
# AGENT: refuse — after removing any copy an earlier run left behind. The scan
# script itself is NOT removed: ${LIB_DIR} is a directory this installer's
# SERVER path also owns, nothing on an agent executes that copy once the units
# are gone, and deleting it would make the agent path a cleaner of state it does
# not own.
# ---------------------------------------------------------------------------
if [ "$ROLE" = agent ]; then
  log "AGENT node: ${SERVICE} is not installed here"
  printf '  reason: %s\n' "$AGENT_REFUSAL_REASON"
  log "Remove any copy an earlier run installed on this node"
  remove_installed_units
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  fi
  die "refusing to install ${SERVICE} on an agent node -- see the reason above"
fi

# ---------------------------------------------------------------------------
# SERVER: the sequence this installer ran before it knew about roles.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
fi
for f in scan-runner-pod-lifecycle.sh "$SERVICE" "$TIMER"; do
  [ -f "${SCRIPT_DIR}/${f}" ] || die "${SCRIPT_DIR}/${f} not found"
done

# ---------------------------------------------------------------------------
log "1. Copy the scan script to ${LIB_DIR}"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/scan-runner-pod-lifecycle.sh" "${LIB_DIR}/scan-runner-pod-lifecycle.sh"

# ---------------------------------------------------------------------------
log "2. Install the service and timer"
run install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
run install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"
run systemctl daemon-reload

# ---------------------------------------------------------------------------
log "3. Enable and start the timer"
run systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "4. Verify"
if [ "$DRY_RUN" -eq 1 ]; then
  run systemctl is-active "${TIMER}"
  run systemctl list-timers --no-pager --all "${TIMER}"
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  exit 0
fi
state="$(systemctl is-active "${TIMER}" 2>/dev/null || true)"
[ "$state" = "active" ] || die "${TIMER} is '${state}', expected 'active'"
systemctl list-timers --no-pager --all "${TIMER}" | head -3

log "DONE. ${TIMER} active; the sweep runs every 5 minutes in report mode."
log "Read findings with: journalctl -u ${SERVICE} -n 60 --no-pager; check state with: systemctl is-failed ${SERVICE}; tell a deadline kill from a finding with: systemctl show -p Result ${SERVICE} (timeout vs exit-code)"
