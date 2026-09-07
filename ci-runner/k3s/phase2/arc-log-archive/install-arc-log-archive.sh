#!/usr/bin/env bash
# install-arc-log-archive.sh — install the ARC log archive on the k3s SERVER
# node: the archive script into /usr/local/lib, then the oneshot service and its
# 2-minute timer into /etc/systemd/system.
#
# WHY A SCRIPT rather than three hand-run `install` commands: the same reasoning
# as the sibling ../wedged-runner/install-wedged-runner-scan.sh. The unit's
# ExecStart path (/usr/local/lib/ci-runner-k3s/archive-arc-logs.sh) is a COPY of
# a script living in this repository, so installing the unit without copying the
# script yields a timer that fires every two minutes and fails every time.
#
# NODE-LOCAL, like its siblings: systemd units are machine state. Re-run after
# any SERVER node rebuild.
#
# SERVER-ONLY, AND IT NOW REFUSES ON AN AGENT (2026-09-07,
# livespec-dev-tooling-qcq0, livespec plan `k3s-on-gmktec-for-vps-usage` carrier
# R3). This one is server-shaped for a DIFFERENT reason from the two scan
# installers beside it, and the difference is worth stating because it is what
# makes the failure quiet rather than loud:
#
#   * archive-arc-logs.service is ordered `After=network-online.target`, NOT
#     `Requires=k3s.service`. So on an agent it installs, enables and starts
#     without complaint — nothing here fails the way the two scans do;
#   * it carries `Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml`, the admin
#     file only a server holds, and archive-arc-logs.sh reads the CONTROLLER and
#     LISTENER pods' logs in the ARC namespace — controller-manager and listener
#     pods that run on the SERVER, for the whole pool. There is nothing on an
#     agent for it to archive and no credential for it to read with, so what an
#     agent gets is a timer that fails silently every two minutes.
#
# The SERVER's own archive-arc-logs.timer already archives those logs for the
# entire pool, so a copy on an agent adds no coverage. It is therefore refused —
# and any copy an earlier run left behind is REMOVED, so a re-run leaves a clean
# host.
#
# WHAT AN AGENT REFUSAL DOES NOT REMOVE: /var/log/arc-archive and
# /var/lib/ci-runner-k3s/arc-log-archive. Those are DATA directories, and a
# removal path that deletes archived logs would be destroying evidence to tidy
# up after an install — the opposite trade from removing a unit that cannot run.
# Empty directories on an agent are inert; remove them by hand if the node's
# disk budget ever cares.
#
# NO MODE ARGUMENT, deliberately, and the contrast with the sibling installer is
# the point. `install-wedged-runner-scan.sh` requires report-vs-clear because
# that choice decides whether the sweep DELETES pods, and a default would be
# making a destructive decision on the operator's behalf. This one only ever
# appends to files under /var/log; there is no destructive variant to choose
# between, so an argument would be ceremony rather than a safeguard.
#
# Requires: root and systemd. `--dry-run` requires neither and executes nothing
# — it is what makes the role decision assertable off-host
# (./install-arc-log-archive-exit-tests.sh).
#
# Usage: install-arc-log-archive.sh [--dry-run] [--role server|agent]
#   --role    the node's cluster role. Defaults to the CLUSTER_ROLE environment
#             variable when set, and to `server` otherwise — which is what a
#             bare invocation meant before this script knew about roles.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="archive-arc-logs.service"
TIMER="archive-arc-logs.timer"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--role server|agent]   (--role defaults to \$CLUSTER_ROLE, then to server)"

AGENT_REFUSAL_REASON="${SERVICE} carries Environment=KUBECONFIG=/etc/rancher/k3s/k3s.yaml (the admin file only a server holds) and archive-arc-logs.sh reads the ARC CONTROLLER and LISTENER pods' logs cluster-wide -- pods that run on the SERVER for the whole pool. The SERVER's own ${TIMER} already archives them for every node, this one included, so an agent copy adds no coverage: it is ordered After=network-online.target rather than Requires=k3s.service, so it starts cleanly here and then fails silently every two minutes with no credential and nothing to read."

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
      # A failed `disable` does not stop the removal: deleting the file is the
      # half that actually clears it. Reported, never silent.
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
# AGENT: refuse — after removing any copy an earlier run left behind. Neither
# the archive script under ${LIB_DIR} nor the two data directories are removed;
# see this script's header for why.
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

# ---------------------------------------------------------------------------
log "1. Install the archive script to ${LIB_DIR} (the unit's ExecStart path)"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/archive-arc-logs.sh" "${LIB_DIR}/archive-arc-logs.sh"

# ---------------------------------------------------------------------------
log "2. Create the archive and state directories"
# 0750 rather than 0755: ARC logs carry installation ids, session uuids, and
# repository names. None of that is a credential, but none of it needs to be
# world-readable on a host that also runs job containers.
run install -d -m 0750 /var/log/arc-archive
run install -d -m 0750 /var/lib/ci-runner-k3s/arc-log-archive

# ---------------------------------------------------------------------------
log "3. Install the unit files"
run install -m 0644 "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
run install -m 0644 "${SCRIPT_DIR}/${TIMER}" "${UNIT_DIR}/${TIMER}"

# ---------------------------------------------------------------------------
log "4. Enable and start the timer"
run systemctl daemon-reload
run systemctl enable --now "${TIMER}"

# ---------------------------------------------------------------------------
log "5. Verify: run one archive pass now and show its output"
run systemctl start "${SERVICE}" || true
run systemctl --no-pager status "${TIMER}" || true
run journalctl -u "${SERVICE}" -n 30 --no-pager || true

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${TIMER} armed; ARC logs archived to /var/log/arc-archive every 2 minutes."
