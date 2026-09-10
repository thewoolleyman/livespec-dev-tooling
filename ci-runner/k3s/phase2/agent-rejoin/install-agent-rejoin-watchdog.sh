#!/usr/bin/env bash
# install-agent-rejoin-watchdog.sh — install the k3s-agent rejoin watchdog on a
# k3s AGENT node: the watchdog script into /usr/local/lib, then the oneshot
# service and its ~60s timer into /etc/systemd/system, and arm the timer.
#
# WHY A SCRIPT rather than three hand-run `install` commands: the same reasoning
# as the sibling ../wedged-runner/install-wedged-runner-scan.sh and
# ../node-extended-resource/install-reapply-unit.sh — the unit's ExecStart path
# /usr/local/lib/ci-runner-k3s/agent-rejoin-watchdog.sh is a COPY of a script in
# this repository, so installing the unit without copying the script yields a
# timer that fires every minute and fails every time. Installation is therefore
# a copy-plus-enable step, and a step done by hand is a step done differently
# twice.
#
# NODE-LOCAL: systemd units are machine state. Re-run after any AGENT node
# rebuild. install-node.sh drives it on the agent path.
#
# AGENT-ONLY, AND IT REFUSES ON A SERVER — the mirror image of the four
# server-only installers in this tree, which refuse on an agent. The watchdog
# restarts a wedged k3s-AGENT so it re-registers after the control-plane
# datastore was wiped; the self-authoritative SERVER holds that datastore and
# never loses its own registration, runs k3s.service rather than
# k3s-agent.service (so the watchdog's first gate is never true there), and would
# gain nothing but a timer firing into a condition that cannot arise. So
# installing it on a server is wrong in KIND, not merely redundant. A server
# invocation therefore REFUSES — and first REMOVES any copy an earlier run left,
# so a re-run leaves a clean host rather than a stray timer.
#
# THE VERIFY ASSERTS on the agent: the timer's ActiveState is READ and CHECKED,
# and anything other than `active` is fatal and names the state it found — the
# lesson of livespec-dev-tooling-qcq0, where a sibling installer printed DONE
# over a timer that had landed `failed`.
#
# Requires (agent, real run): root and systemd. `--dry-run` requires neither and
# executes nothing — it is what makes the role decision assertable off-host
# (./install-agent-rejoin-watchdog-exit-tests.sh).
#
# Usage: install-agent-rejoin-watchdog.sh [--dry-run] [--role server|agent]
#   --role  the node's cluster role. Defaults to the CLUSTER_ROLE environment
#           variable when set, and to `server` otherwise — so a bare invocation
#           refuses rather than installing an agent-only unit by accident.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
WATCHDOG="agent-rejoin-watchdog.sh"
SERVICE="agent-rejoin-watchdog.service"
TIMER="agent-rejoin-watchdog.timer"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--role server|agent]   (--role defaults to \$CLUSTER_ROLE, then to server; the watchdog is AGENT-ONLY and a server invocation refuses)"

SERVER_REFUSAL_REASON="${SERVICE} restarts a wedged k3s-AGENT so it re-registers after the control-plane datastore was wiped. A SERVER holds that datastore and never loses its own registration, runs k3s.service not k3s-agent.service (the watchdog's first gate is never true there), and would gain only a timer firing into a condition that cannot arise. The rejoin watchdog belongs on the AGENTS this server serves, not here."

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
    *)  die "unexpected extra argument '$1' -- ${USAGE}" ;;
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

# The second READ, asked only of a unit this node does NOT carry: `systemctl
# is-failed` prints `failed` for a unit in the failed state INCLUDING one whose
# file is gone (`not-found failed`), so the ANSWER is compared rather than the
# exit code. A deleted unit keeps that state until reset-failed or a reboot
# (livespec-dev-tooling-ssbg).
unit_failed() {  # unit_failed NAME
  command -v systemctl >/dev/null 2>&1 || return 1
  [ "$(systemctl is-failed "$1" 2>/dev/null)" = failed ]
}

# `systemctl show -p ActiveState` and not `is-active`, because the WORD is the
# diagnosis the operator needs. A dry run has enabled nothing, so it prints the
# read and returns.
assert_timer_active() {
  local state
  if [ "$DRY_RUN" -eq 1 ]; then
    run systemctl show -p ActiveState --value "${TIMER}"
    return 0
  fi
  state="$(systemctl show -p ActiveState --value "${TIMER}" 2>/dev/null || true)"
  state="${state:-<no answer>}"
  printf '+ systemctl show -p ActiveState --value %s -> %s\n' "${TIMER}" "${state}"
  [ "$state" = active ] || die "${TIMER} is '${state}', expected 'active' -- ${SERVICE} is NOT armed on this node. Read 'systemctl status ${SERVICE}' and 'journalctl -u ${SERVICE}'."
}

# The timer BEFORE the service it triggers, so nothing fires between the two.
# The watchdog SCRIPT in ${LIB_DIR} is NOT removed here: that directory is shared
# with the server-path installers of this tree, nothing on a server executes the
# agent watchdog once its units are gone, and deleting it would make this path a
# cleaner of state it does not own.
remove_installed_units() {
  local unit removed_units=() stale_failed_units=()
  for unit in "$TIMER" "$SERVICE"; do
    if unit_installed "$unit"; then
      removed_units+=("$unit")
      run systemctl disable --now "$unit" \
        || printf '  disable failed for %s -- removing the unit file anyway\n' "$unit"
      run rm -f "${UNIT_DIR}/${unit}"
    elif unit_failed "$unit"; then
      stale_failed_units+=("$unit")
    fi
  done
  if [ "${#removed_units[@]}" -gt 0 ]; then
    run systemctl daemon-reload
    for unit in "${removed_units[@]}"; do
      run systemctl reset-failed "$unit" \
        || printf '  reset-failed found no %s to clear -- systemd had already forgotten it\n' "$unit"
    done
  fi
  if [ "${#stale_failed_units[@]}" -gt 0 ]; then
    for unit in "${stale_failed_units[@]}"; do
      run systemctl reset-failed "$unit" \
        || printf '  reset-failed found no %s to clear -- systemd had already forgotten it\n' "$unit"
    done
  elif [ "${#removed_units[@]}" -eq 0 ]; then
    printf '  nothing to remove: neither %s nor %s is installed on this node, and neither is failed\n' \
      "$SERVICE" "$TIMER"
  fi
}

# ---------------------------------------------------------------------------
# SERVER: refuse — after removing any copy an earlier run left behind.
# ---------------------------------------------------------------------------
if [ "$ROLE" = server ]; then
  log "SERVER node: ${SERVICE} is not installed here"
  printf '  reason: %s\n' "$SERVER_REFUSAL_REASON"
  log "Remove any copy an earlier run installed on this node"
  remove_installed_units
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  fi
  die "refusing to install ${SERVICE} on a server node -- see the reason above"
fi

# ---------------------------------------------------------------------------
# AGENT: install the watchdog and arm its timer.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
fi

log "1. Install the watchdog script to ${LIB_DIR} (the unit's ExecStart path)"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/${WATCHDOG}" "${LIB_DIR}/${WATCHDOG}"

log "2. Install the unit files"
run install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
run install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"

log "3. Enable and start the timer"
run systemctl daemon-reload
run systemctl enable --now "${TIMER}"

log "4. Verify: the timer is armed"
run systemctl --no-pager status "${TIMER}" || true
assert_timer_active

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${TIMER} armed; ${SERVICE} checks for a wedged k3s-agent every ~60s and restarts it to force re-registration when the wedge is unambiguous."
