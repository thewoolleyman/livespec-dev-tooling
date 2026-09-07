#!/usr/bin/env bash
# remove-server-only-units.sh — disable and delete named SERVER-ONLY systemd
# units from the node this runs on, reload systemd once, then clear the FAILED
# state of every named unit that has one — the ones just removed AND the ones
# an EARLIER run already removed. Idempotent: a unit that is neither installed
# nor failed here is not mentioned, and a run that finds nothing to do says so.
#
# WHY THE reset-failed. Deleting a unit file and reloading does NOT take the
# unit out of `systemctl list-units --state=failed`: systemd keeps the failed
# state in the manager, and a unit whose file is gone is reported there as
# `not-found failed` until `systemctl reset-failed` runs or the host reboots.
# Measured on gmktec-xubuntu 2026-09-07 (livespec-dev-tooling-oc5g): a run of
# this script exited 0, every unit file was gone and `is-enabled` said
# `not-found` for each — and the three timers were still listed failed. So a
# failed-units read on that agent stayed red, which is a false monitoring
# signal AND residual drift this very runbook created. `reset-failed` on a unit
# systemd no longer knows is an error, not a no-op, so its failure is reported
# and tolerated rather than allowed to fail the run.
#
# WHY THE CLEAR IS OVER THE UNITS NAMED AND NOT THE UNITS REMOVED. That first
# reset-failed pass ran over exactly the units removed IN THE SAME INVOCATION,
# which cannot converge the host it was written for: gmktec-xubuntu's unit files
# were deleted by the run BEFORE reset-failed existed, so by the time the pass
# shipped there was nothing left to remove and therefore nothing to clear.
# Measured on that node 2026-09-07 at tree c13617d0, with the pass in place:
# this script reported `nothing to remove: none of the 6 server-only units named
# is installed on this node` while `systemctl list-units --state=failed` still
# listed reapply-node-extended-resource.timer, scan-wedged-runners.timer and
# scan-runner-pod-lifecycle.timer as `not-found failed`
# (livespec-dev-tooling-ssbg). A residual failed state is drift whoever created
# it, and this script is the runbook's one convergence point for these unit
# names — so every NAMED unit that is not installed here is asked
# `systemctl is-failed` and cleared when the answer is `failed`. That probe is
# a READ, so a dry run performs it (unprivileged) and executes nothing.
#
# WHY THIS EXISTS, when four installers already remove their own units.
# ../phase2's server-only installers each REFUSE on an agent and, before
# refusing, remove any copy an earlier run left behind
# (livespec-dev-tooling-ukbp, livespec-dev-tooling-qcq0). That cleanup is
# reached only by INVOKING the installer — and ./install-node.sh's agent plan
# does not invoke those installers at all: it SKIPs the steps. So on the one
# node where the stale units actually are, the removal never ran. Measured on
# gmktec-xubuntu 2026-09-07, after a full runbook run that exited 0:
# reapply-node-extended-resource.timer, scan-wedged-runners.timer and
# scan-runner-pod-lifecycle.timer were still `enabled` and `failed` with
# `Unit k3s.service not found` (livespec-dev-tooling-43sc). A host carrying
# units it cannot run is exactly the drift the "CI host as reconstructible
# cattle" goal forbids, so the SKIP has to clean up after the runs that
# installed them.
#
# It is a SEPARATE script rather than a fifth `--remove-stale` flag on four
# installers because the caller is a SKIP: the runbook needs a removal it can
# invoke without asking an installer to refuse (each of those refusals is a
# non-zero exit, which is right for a direct invocation and wrong for a step
# the plan deliberately omits), and it needs ONE daemon-reload over the whole
# set rather than one per installer. The four installers keep their own
# removal for the direct-invocation path; this one serves install-node.sh's
# skip path. Both write the same sequence, and install-node-exit-tests.sh
# asserts the unit NAMES agree with the installers that own them, so the two
# cannot drift apart silently.
#
# WHAT IT DOES NOT DO. It removes UNIT FILES only — never the scripts under
# /usr/local/lib/ci-runner-k3s that those units exec, for the reason each
# installer gives: nothing on an agent executes those copies, and a remover
# that deleted them would be cleaning up state it does not own.
#
# Requires root, and systemd, when it actually has something to do — a removal
# or a clear. `--dry-run` requires neither and executes nothing — it prints the
# exact sequence this
# host needs as `+ ` lines, which is what makes this script assertable off-host
# (./remove-server-only-units-exit-tests.sh) and the runbook's skip path with it
# (./install-node-exit-tests.sh).
#
# Usage: remove-server-only-units.sh [--dry-run] UNIT...
#   UNIT  a systemd unit NAME (`foo.service`, `foo.timer`), not a path. Pass
#         each timer BEFORE the service it triggers, so nothing can fire
#         between the two removals.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
UNIT_DIR="/etc/systemd/system"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] UNIT...   (UNIT = a systemd unit name such as scan-wedged-runners.timer; pass each timer before the service it triggers)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
UNITS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *) UNITS+=("$1") ;;
  esac
  shift
done

[ "${#UNITS[@]}" -gt 0 ] || die "no unit named -- ${USAGE}"

# A NAME, never a path: this script deletes ${UNIT_DIR}/${unit}, so anything
# that could climb out of that directory is refused before it is joined to it.
for unit in "${UNITS[@]}"; do
  if ! [[ "$unit" =~ ^[A-Za-z0-9][A-Za-z0-9@._-]*\.(service|timer)$ ]]; then
    die "'${unit}' is not a systemd unit name (want NAME.service or NAME.timer) -- ${USAGE}"
  fi
done

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
# in place, which is how gmktec ended up with enabled units that could not
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

# The second READ, asked only of the units this node does NOT carry, and
# performed under --dry-run for the same reason as the first: an unprivileged
# caller may ask systemd for a state, and the sequence a dry run prints has to
# be the one this host actually needs. `systemctl is-failed` prints `failed` for
# a unit in the failed state INCLUDING one whose file is gone — that is the
# `not-found failed` this script exists to clear — and prints `inactive`,
# `unknown` or nothing at all otherwise, so the answer is compared rather than
# the exit code.
unit_failed() {  # unit_failed NAME
  command -v systemctl >/dev/null 2>&1 || return 1
  [ "$(systemctl is-failed "$1" 2>/dev/null)" = failed ]
}

# The live path mutates the node, so it needs root and a systemd — but only
# once something is actually going to be done, so a node that needs nothing
# requires neither. Called at the first unit that earns a command, whether that
# command is a removal or a bare reset-failed.
privileges_checked=0
require_live_privileges() {
  [ "$DRY_RUN" -eq 0 ] || return 0
  [ "$privileges_checked" -eq 0 ] || return 0
  privileges_checked=1
  [ "$(id -u)" -eq 0 ] \
    || die "must run as root (removes unit files from ${UNIT_DIR} and clears failed state)"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
}

# ONE call site for the clear, so the removed units' pass and the residual pass
# cannot drift apart. Tolerant of a non-zero exit, which is what `reset-failed`
# returns for a unit the manager no longer knows: nothing here is worth failing
# a cleanup over, and the failure is reported rather than swallowed.
clear_failed_state() {  # clear_failed_state NAME
  run systemctl reset-failed "$1" \
    || printf '  reset-failed found no %s to clear -- systemd had already forgotten it\n' "$1"
}

# ---------------------------------------------------------------------------
# The removal. Units are taken in the order given — the caller's job is to put
# each timer before the service it triggers — and systemd is reloaded ONCE, at
# the end, only if something was actually removed. Each named unit lands in
# exactly one of two lists, IN THE ORDER GIVEN: the ones removed by this run,
# and the ones this node does not carry but systemd still reports failed. Both
# lists are cleared below; they differ only in whether a reload has to come
# first.
# ---------------------------------------------------------------------------
removed_units=()
stale_failed_units=()
for unit in "${UNITS[@]}"; do
  if unit_installed "$unit"; then
    require_live_privileges
    removed_units+=("$unit")
    # A failed `disable` does not stop the removal: the units this cleans up
    # after are ones systemd could not start in the first place, and deleting the
    # file is the half that actually clears it. Reported, never silent.
    run systemctl disable --now "$unit" \
      || printf '  disable failed for %s -- removing the unit file anyway\n' "$unit"
    run rm -f "${UNIT_DIR}/${unit}"
  elif unit_failed "$unit"; then
    require_live_privileges
    stale_failed_units+=("$unit")
  fi
done

# AFTER the reload, so systemd has already been told the files are gone. See
# this script's header for why the step exists at all.
if [ "${#removed_units[@]}" -gt 0 ]; then
  run systemctl daemon-reload
  for unit in "${removed_units[@]}"; do
    clear_failed_state "$unit"
  done
fi

# The RESIDUAL clear, and no reload before it: nothing on this node changed —
# these unit files were already gone when this run started, which is exactly
# how gmktec-xubuntu was found (livespec-dev-tooling-ssbg). A run that removed
# nothing but cleared something is NOT a "nothing to remove" run, so the two
# are alternatives: the reset lines are the output when there are any.
if [ "${#stale_failed_units[@]}" -gt 0 ]; then
  for unit in "${stale_failed_units[@]}"; do
    clear_failed_state "$unit"
  done
elif [ "${#removed_units[@]}" -eq 0 ]; then
  printf '  nothing to remove: none of the %s server-only units named is installed on this node, and none is failed\n' \
    "${#UNITS[@]}"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
fi
