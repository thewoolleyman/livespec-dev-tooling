#!/usr/bin/env bash
# install-wedged-runner-scan.sh — install the wedged-runner sweep on the k3s
# SERVER node: the scan script into /usr/local/lib, then the oneshot service
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
# systemd units are machine state. Re-run after any SERVER node rebuild.
#
# SERVER-ONLY, AND IT NOW REFUSES ON AN AGENT (2026-09-07,
# livespec-dev-tooling-qcq0, livespec plan `k3s-on-gmktec-for-vps-usage` carrier
# R3). Run on gmktec-xubuntu — the fleet's first agent — this installer put both
# units on the host, enabled the timer, and then reported DONE anyway, because
# the service is server-shaped THREE ways and an agent satisfies none of them:
#
#   * it is ordered `After=`/`Requires=k3s.service`, and an agent runs
#     `k3s-agent.service`, so `systemctl start` fails with "Unit k3s.service not
#     found" and the timer lands `failed (Result: resources)`;
#   * it carries `Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml`, the admin
#     file only a server holds;
#   * scan-wedged-runners.sh sweeps the ARC runner pods CLUSTER-WIDE — every
#     pod in the runners namespace, on every node — so running it is a POOL-WIDE
#     duty rather than a node-local one. The SERVER's own scan-wedged-runners.timer
#     already performs exactly that sweep every five minutes, and it already
#     covers this node's pods; a second copy on the agent would be a second
#     sweeper of the same pods with a credential it does not have.
#
# So installing this on an agent is wrong in KIND, not merely misconfigured. An
# agent invocation therefore REFUSES — and, because the pre-refusal run left
# both units enabled on gmktec, it first REMOVES any copy it finds, so a re-run
# leaves a clean host instead of a dead timer.
#
# MODE IS REQUIRED ON A SERVER AND NOT DEFAULTED, and the reason is a real
# decision rather than caution-by-habit:
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
# precisely because that answer is per host. An agent invocation needs no mode,
# because it installs nothing.
#
# THE VERIFY ASSERTS, IT NO LONGER MERELY DISPLAYS (the second half of
# livespec-dev-tooling-qcq0). Until now step 4 ran `systemctl status` and
# `journalctl` with `|| true` and then printed "DONE. timer armed" whatever they
# said — which is how the gmktec run reported an armed timer that was in fact
# `failed (Result: resources)`. The timer's ActiveState is now READ and CHECKED:
# anything other than `active` is fatal and names the state it found. The
# SERVICE's own exit status is still not a verdict, because in `report` mode a
# genuine finding exits non-zero by design.
#
# Requires: root, systemd, and the same KUBECONFIG the service itself uses.
# `--dry-run` requires none of them and executes nothing — it is what makes the
# role decision assertable off-host (./install-wedged-runner-scan-exit-tests.sh).
#
# Usage: install-wedged-runner-scan.sh [--dry-run] [--role server|agent] [MODE]
#   MODE      'report' or 'clear' -- see this script's header; required for a
#             server, refused-with-the-role for an agent
#   --role    the node's cluster role. Defaults to the CLUSTER_ROLE environment
#             variable when set, and to `server` otherwise — which is what a
#             bare invocation meant before this script knew about roles.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="scan-wedged-runners.service"
TIMER="scan-wedged-runners.timer"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--role server|agent] [MODE]   (MODE is 'report' or 'clear', required on a server -- see this script's header; --role defaults to \$CLUSTER_ROLE, then to server)"

AGENT_REFUSAL_REASON="${SERVICE} is SERVER-SHAPED and an agent satisfies none of it: Requires=k3s.service (an agent runs k3s-agent.service, so the unit cannot even start), Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml (the admin file only a server holds), and scan-wedged-runners.sh sweeps the ARC runner pods CLUSTER-WIDE -- a pool-wide duty the SERVER's own ${TIMER} already performs every five minutes over every pod on every node, this one included."

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
ROLE=""
ROLE_GIVEN=0
MODE=""

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
      [ -z "$MODE" ] || die "unexpected extra argument '$1' -- ${USAGE}"
      MODE="$1" ;;
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
# in place, which is how gmktec ended up with an enabled timer that could not
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

# THE ASSERTION THIS INSTALLER DID NOT HAVE. `systemctl show -p ActiveState` and
# not `is-active`, because the WORD is the diagnosis the operator needs: on
# gmktec the timer read `failed` (the service it triggers could not start at
# all), and `inactive` would have meant something else entirely. A dry run has
# enabled nothing, so there is nothing for it to assert — it prints the read and
# returns, exactly as it prints every other command it does not execute.
assert_timer_active() {
  local state
  if [ "$DRY_RUN" -eq 1 ]; then
    run systemctl show -p ActiveState --value "${TIMER}"
    return 0
  fi
  state="$(systemctl show -p ActiveState --value "${TIMER}" 2>/dev/null || true)"
  state="${state:-<no answer>}"
  printf '+ systemctl show -p ActiveState --value %s -> %s\n' "${TIMER}" "${state}"
  [ "$state" = active ] || die "${TIMER} is '${state}', expected 'active' -- ${SERVICE} is NOT armed on this node. A '${TIMER}' that lands 'failed' means the service it triggers could not start: read 'systemctl status ${SERVICE}' and 'journalctl -u ${SERVICE}'."
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
[ -n "$MODE" ] || die "no MODE given -- ${USAGE}"
case "$MODE" in
  report) MODE_ARG="" ;;
  clear)  MODE_ARG="--clear" ;;
  *)      die "MODE must be 'report' or 'clear', got '${MODE}'" ;;
esac

if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
fi

# ---------------------------------------------------------------------------
log "1. Install the scan script to ${LIB_DIR} (the unit's ExecStart path)"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/scan-wedged-runners.sh" "${LIB_DIR}/scan-wedged-runners.sh"

# ---------------------------------------------------------------------------
log "2. Install the unit files, substituting mode=${MODE}"
# The substitution writes a STAGED copy which `install` then puts in place,
# rather than sed writing ${UNIT_DIR}/${SERVICE} directly with chmod fixing the
# mode afterwards. Three reasons, and none of them is cosmetic: a sed that fails
# half way leaves the LIVE unit untouched instead of truncated; the mode arrives
# WITH the file rather than in a second step; and it leaves this installer with
# no command that writes outside a temporary directory except through `install`,
# which is what lets the exit tests drive the whole SERVER path — the verify
# included — against stubs.
#
# A dry run stages nothing, so it names the staging directory `<staged>`: that
# keeps the printed sequence deterministic AND keeps it a faithful description
# of the real run, which prints the same two lines with the real path in them.
if [ "$DRY_RUN" -eq 1 ]; then
  STAGE_DIR="<staged>"
else
  STAGE_DIR="$(mktemp -d)"
  trap 'rm -rf "${STAGE_DIR}"' EXIT
fi
# The one step with a redirect, so it is printed here rather than routed through
# `run`; the printf and the sed below are the same command written twice, on
# purpose.
printf '+ sed s|MODE_PLACEHOLDER|%s| %s > %s\n' "${MODE_ARG}" "${SCRIPT_DIR}/${SERVICE}" "${STAGE_DIR}/${SERVICE}"
if [ "$DRY_RUN" -eq 0 ]; then
  sed "s|MODE_PLACEHOLDER|${MODE_ARG}|" "${SCRIPT_DIR}/${SERVICE}" > "${STAGE_DIR}/${SERVICE}"
  # Fail loudly rather than installing a unit that would fail every five minutes.
  if grep -q MODE_PLACEHOLDER "${STAGE_DIR}/${SERVICE}"; then
    die "MODE_PLACEHOLDER survived substitution in ${STAGE_DIR}/${SERVICE}"
  fi
fi
run install -m 0644 "${STAGE_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
run install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"

# ---------------------------------------------------------------------------
log "3. Enable and start the timer"
run systemctl daemon-reload
run systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "4. Verify: the timer is armed, and one sweep's output"
# `|| true` on the START because in report mode a genuine finding EXITS NON-ZERO
# by design, and an installer that aborted on a true positive would be reporting
# the install as broken when it is in fact working. The TIMER's state carries no
# such ambiguity, so it is asserted below rather than displayed.
run systemctl start "${SERVICE}" || true
run systemctl --no-pager status "${TIMER}" || true
run journalctl -u "${SERVICE}" -n 40 --no-pager || true
assert_timer_active

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${TIMER} armed; ${SERVICE} sweeps for wedged runners every 5 minutes in '${MODE}' mode."
