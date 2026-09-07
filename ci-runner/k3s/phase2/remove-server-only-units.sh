#!/usr/bin/env bash
# remove-server-only-units.sh — disable and delete named SERVER-ONLY systemd
# units from the node this runs on, then reload systemd once. Idempotent: a
# unit that is not installed here is not mentioned, and a run that finds
# nothing removes nothing and says so.
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
# Requires root, and systemd, when it actually removes something. `--dry-run`
# requires neither and executes nothing — it prints the exact sequence this
# host needs as `+ ` lines, which is what makes the runbook's skip path
# assertable off-host (./install-node-exit-tests.sh).
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

# ---------------------------------------------------------------------------
# The removal. Units are taken in the order given — the caller's job is to put
# each timer before the service it triggers — and systemd is reloaded ONCE, at
# the end, only if something was actually removed.
# ---------------------------------------------------------------------------
removed=0
for unit in "${UNITS[@]}"; do
  unit_installed "$unit" || continue
  if [ "$removed" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
    [ "$(id -u)" -eq 0 ] || die "must run as root (removes unit files from ${UNIT_DIR})"
    command -v systemctl >/dev/null || die "systemctl not found on PATH"
  fi
  removed=1
  # A failed `disable` does not stop the removal: the units this cleans up
  # after are ones systemd could not start in the first place, and deleting the
  # file is the half that actually clears it. Reported, never silent.
  run systemctl disable --now "$unit" \
    || printf '  disable failed for %s -- removing the unit file anyway\n' "$unit"
  run rm -f "${UNIT_DIR}/${unit}"
done

if [ "$removed" -eq 1 ]; then
  run systemctl daemon-reload
else
  printf '  nothing to remove: none of the %s server-only units named is installed on this node\n' \
    "${#UNITS[@]}"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
fi
