#!/usr/bin/env bash
# install-reapply-unit.sh — install the ci-runner.io/churn-slot reapply
# insurance on the k3s SERVER node: the patch script into /usr/local/lib, then
# the oneshot service and its 5-minute timer into /etc/systemd/system, with
# CAPACITY_PLACEHOLDER substituted for the capacity this node is intended to
# carry.
#
# WHY A SCRIPT rather than three hand-run `install` commands: the unit file
# shipped in this tree is deliberately NOT runnable as-is — its ExecStart says
# `CAPACITY_PLACEHOLDER` so that an un-edited copy fails loudly instead of
# silently reapplying a wrong number (see reapply-node-extended-resource.service's
# own header). That design makes installation a substitution step, and a
# substitution step done by hand is a step that gets done differently twice. It
# also encodes the dependency the unit file cannot state: the ExecStart path
# /usr/local/lib/ci-runner-k3s/patch-node-churn-capacity.sh is a COPY of a script
# living in this repository, so installing the unit without copying the script
# yields a timer that fires every five minutes and fails every time.
#
# NODE-LOCAL, like install-apparmor-profile.sh: systemd units are machine state.
# Re-run on any SERVER node rebuild.
#
# SERVER-ONLY, AND IT NOW REFUSES ON AN AGENT (2026-09-07,
# livespec-dev-tooling-ukbp, livespec plan `k3s-on-gmktec-for-vps-usage` carrier
# R3). Run on gmktec-xubuntu — the fleet's first agent — this installer put both
# units on the host and then died at its own verify step, because the service is
# server-shaped THREE ways and an agent satisfies none of them:
#
#   * it is ordered `After=`/`Requires=k3s.service`, and an agent runs
#     `k3s-agent.service`, so `systemctl start` fails with "Unit k3s.service not
#     found" — which is what took ../install-node.sh's whole runbook down at step
#     4 of 10, before six later steps that had nothing to do with this one;
#   * it carries `Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml`, the admin
#     file only a server holds;
#   * patch-node-churn-capacity.sh patches EVERY node matching
#     `k3s-role=arc-runner-host` with ONE capacity, so applying it is a
#     CLUSTER-WIDE act rather than a node-local one. The SERVER's reapply timer
#     already performs exactly that act every five minutes, and since
#     ../../provision-k3s.sh labels every pool node, its selector already
#     includes the agent. A second copy of the timer on the agent would reapply
#     the same cluster-wide patch with that node's own number.
#
# So installing this on an agent is wrong in KIND, not merely misconfigured, and
# no amount of role-conditional unit ordering fixes it: what an agent needs is a
# per-node capacity read from each node's own profile, which is the plan's R4/R5
# scope (livespec-dev-tooling-xa6o) and not this unit. An agent invocation
# therefore REFUSES — and, because the pre-refusal run left the units enabled on
# gmktec, it first REMOVES any copy it finds, so a re-run leaves a clean host
# instead of a failing service and a dead timer.
#
# The capacity argument is REQUIRED on a server and is not defaulted, for
# exactly the reason patch-node-churn-capacity.sh does not default it: the safe
# number was a measurement, not a constant (see that script's header and
# ../kueue/DERIVATION.md). This unit makes an ALREADY-DECIDED number durable
# across restarts; it does not decide it. An agent invocation needs no capacity,
# because it installs nothing.
#
# BOTH the timer AND the service are enabled (2026-09-02): the service is
# WantedBy=multi-user.target and Before=converge-ci-stack.service so a boot
# applies the resource before the queues that are denominated in it; the
# timer keeps reconciling it every five minutes after that.
#
# Requires: root, systemd, and the same KUBECONFIG the service itself uses.
# `--dry-run` requires none of them and executes nothing — it is what makes the
# role decision assertable off-host (./install-reapply-unit-exit-tests.sh).
#
# Usage: install-reapply-unit.sh [--dry-run] [--role server|agent] [CAPACITY]
#   CAPACITY  the currently-intended ci-runner.io/churn-slot node capacity;
#             required for a server, refused-with-the-role for an agent
#   --role    the node's cluster role. Defaults to the CLUSTER_ROLE environment
#             variable when set, and to `server` otherwise — which is what a
#             bare invocation meant before this script knew about roles.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="reapply-node-extended-resource.service"
TIMER="reapply-node-extended-resource.timer"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--role server|agent] [CAPACITY]   (CAPACITY = the currently-intended ci-runner.io/churn-slot node capacity, required on a server -- see this script's header; --role defaults to \$CLUSTER_ROLE, then to server)"

AGENT_REFUSAL_REASON="${SERVICE} is SERVER-SHAPED and an agent satisfies none of it: Requires=k3s.service (an agent runs k3s-agent.service), Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml (the admin file only a server holds), and patch-node-churn-capacity.sh patches EVERY node labeled k3s-role=arc-runner-host with ONE capacity -- a cluster-wide act the server's reapply timer already performs every five minutes, over a selector that already includes this node. A per-node capacity read from each node's own profile is R4/R5 scope (livespec-dev-tooling-xa6o), not this unit."

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
ROLE=""
ROLE_GIVEN=0
CAPACITY=""

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
    *)
      [ -z "$CAPACITY" ] || die "unexpected extra argument '$1' -- ${USAGE}"
      CAPACITY="$1" ;;
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
# in place, which is how gmktec ended up with an enabled service that could not
# start.
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
  local unit removed_units=()
  for unit in "$TIMER" "$SERVICE"; do
    if unit_installed "$unit"; then
      removed_units+=("$unit")
      # A failed `disable` does not stop the removal: the unit this cleans up
      # after is one systemd could not start in the first place, and deleting
      # the file is the half that actually clears it. Reported, never silent.
      run systemctl disable --now "$unit" \
        || printf '  disable failed for %s -- removing the unit file anyway\n' "$unit"
      run rm -f "${UNIT_DIR}/${unit}"
    fi
  done
  if [ "${#removed_units[@]}" -gt 0 ]; then
    run systemctl daemon-reload
    # AFTER the reload, and tolerant of a non-zero exit: deleting a unit file
    # and reloading does NOT take the unit out of `systemctl list-units
    # --state=failed` -- systemd keeps the failed state in the manager and
    # reports the deleted unit as `not-found failed` until `reset-failed` runs
    # or the host reboots (livespec-dev-tooling-oc5g, measured on
    # gmktec-xubuntu 2026-09-07). `reset-failed` on a unit the manager no
    # longer knows is itself an error, which is exactly the removed-but-never-
    # failed case, so it is reported rather than allowed to fail this cleanup.
    for unit in "${removed_units[@]}"; do
      run systemctl reset-failed "$unit" \
        || printf '  reset-failed found no %s to clear -- systemd had already forgotten it\n' "$unit"
    done
  else
    printf '  nothing to remove: neither %s nor %s is installed on this node\n' "$SERVICE" "$TIMER"
  fi
}

# ---------------------------------------------------------------------------
# AGENT: refuse — after removing any copy an earlier run left behind. The
# patch script itself is NOT removed: ../reconstruct/ and the converge read
# ${LIB_DIR} on a server only, nothing on an agent executes that copy, and
# deleting a file this installer's server path also owns would make the agent
# path a cleaner of state it does not own.
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
[ -n "$CAPACITY" ] || die "no CAPACITY given -- ${USAGE}"
[[ "$CAPACITY" =~ ^[0-9]+$ ]] || die "CAPACITY must be a non-negative integer, got '${CAPACITY}'"

if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
fi
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

# ---------------------------------------------------------------------------
log "1. Install the patch script to ${LIB_DIR} (the unit's ExecStart path)"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/patch-node-churn-capacity.sh" "${LIB_DIR}/patch-node-churn-capacity.sh"

# ---------------------------------------------------------------------------
log "2. Install the unit files, substituting capacity=${CAPACITY}"
# The substitution is the one step with a redirect, so it is printed rather than
# routed through `run`; the `sed` below and the line printed here are the same
# command written twice, on purpose, and neither is reachable in the other's
# mode.
if [ "$DRY_RUN" -eq 1 ]; then
  printf '+ sed s|CAPACITY_PLACEHOLDER|%s| %s > %s\n' "${CAPACITY}" "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
else
  sed "s|CAPACITY_PLACEHOLDER|${CAPACITY}|" "${SCRIPT_DIR}/${SERVICE}" > "${UNIT_DIR}/${SERVICE}"
  chmod 0644 "${UNIT_DIR}/${SERVICE}"
  # Fail loudly rather than installing a unit that would fail every five minutes.
  if grep -q CAPACITY_PLACEHOLDER "${UNIT_DIR}/${SERVICE}"; then
    die "CAPACITY_PLACEHOLDER survived substitution in ${UNIT_DIR}/${SERVICE}"
  fi
fi
run install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"

# ---------------------------------------------------------------------------
log "3. Enable the service at boot and enable + start the timer"
run systemctl daemon-reload
run systemctl enable "${SERVICE}"
run systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "4. Verify: run the service once now and read the resulting capacity back"
run systemctl start "${SERVICE}"
run systemctl --no-pager status "${TIMER}" || true
run kubectl get nodes -l k3s-role=arc-runner-host \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}'

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${TIMER} armed; ${SERVICE} reapplies capacity=${CAPACITY} at boot (before the converge) and every 5 minutes."
