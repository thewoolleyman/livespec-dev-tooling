#!/usr/bin/env bash
# install-reapply-unit.sh — install THIS node's ci-runner.io/churn-slot reapply
# insurance: the patch script and a copy of the node's PROFILE into
# /usr/local/lib/ci-runner-k3s, then the oneshot service and its 5-minute timer
# into /etc/systemd/system, with the node's k3s unit and profile path
# substituted into the service.
#
# PROFILE-DRIVEN, AND IT NOW INSTALLS ON BOTH ROLES (2026-09-11,
# livespec-dev-tooling-xa6o, livespec plan k3s-on-gmktec-for-vps-usage carrier
# R5). Until R5 this installer REFUSED on an agent, for three reasons that were
# all really one: the reapply mechanism was CLUSTER-WIDE — patch-node-churn-capacity.sh
# resolved its targets with `kubectl get nodes -l k3s-role=arc-runner-host` (a
# LIST) and patched every node with one capacity, the unit was ordered
# Requires=k3s.service, and it carried the server's admin KUBECONFIG. R5 made the
# mechanism PER-NODE: the patch script patches the SINGLE node its profile NAMES
# with the capacity the profile DECLARES, and it derives its credential from the
# profile's role. So an agent CAN now run a node-local timer — ordered against
# k3s-agent.service, authenticating with the scoped node-status kubeconfig the
# ../node-status-credential/ directory mints — and this installer installs it.
#
# WHY A SCRIPT rather than three hand-run `install` commands: the unit file
# shipped in this tree is deliberately NOT runnable as-is — its ExecStart names
# PROFILE_PATH_PLACEHOLDER and its ordering names K3S_UNIT_PLACEHOLDER, so an
# un-edited copy fails loudly instead of silently patching the wrong node from
# the wrong k3s unit. That design makes installation a substitution step, and a
# substitution step done by hand is a step that gets done differently twice. It
# also encodes the dependency the unit file cannot state: the ExecStart path
# /usr/local/lib/ci-runner-k3s/patch-node-churn-capacity.sh is a COPY of a script
# in this repository, and the profile it reads is a COPY of the node's committed
# profile, so installing the unit without copying both yields a timer that fires
# every five minutes and fails every time.
#
# NODE-LOCAL, like install-apparmor-profile.sh: systemd units are machine state.
# Re-run on any node rebuild. THE ARGUMENT IS A PROFILE, not a capacity: the safe
# number is ADMISSION_CAPACITY_C in the node's own profile (a measurement, not a
# constant — see ../kueue/DERIVATION.md), read the same way install-node.sh reads
# it, so this installer and the node's provisioning cannot drift.
#
# Requires: root, systemd, and — for the immediate verify on a server — the admin
# KUBECONFIG. On an agent whose node-status kubeconfig is not seeded yet the units
# are installed and enabled but the immediate verify start is SKIPPED with a
# warning: the timer heals it once the credential lands (seed it with
# ../../secret-reinjection/seed-node-status-kubeconfig.sh). `--dry-run` requires
# none of them and executes nothing — it is what makes the installed sequence
# assertable off-host (./install-reapply-unit-exit-tests.sh).
#
# Usage: install-reapply-unit.sh [--dry-run] PROFILE
#   PROFILE  path to the node's phase0-bare-metal/profiles/<node>.env, which
#            carries NODE_NAME, CLUSTER_ROLE, ADMISSION_CAPACITY_C and
#            CHURN_KUBECONFIG_FILE.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="reapply-node-extended-resource.service"
TIMER="reapply-node-extended-resource.timer"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries NODE_NAME, CLUSTER_ROLE, ADMISSION_CAPACITY_C and CHURN_KUBECONFIG_FILE)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
PROFILE_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      [ -z "$PROFILE_ARG" ] || die "unexpected extra argument '$1' -- ${USAGE}"
      PROFILE_ARG="$1" ;;
  esac
  shift
done

[ -n "$PROFILE_ARG" ] || die "no profile given -- ${USAGE}"
[ -f "$PROFILE_ARG" ] || die "profile not found: ${PROFILE_ARG} -- ${USAGE}"

# ---------------------------------------------------------------------------
# Profile: parsed through the SAME parser the node's own provisioning reads it
# with, never sourced. (The installed COPY of the patch script reads its keys with
# `sed` instead, because profile.sh is not shipped into ${LIB_DIR}; here in the
# repo tree the parser is present, so this installer uses it.)
# ---------------------------------------------------------------------------
# shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
source "${K3S_DIR}/phase0-bare-metal/profile.sh"
profile_load "$PROFILE_ARG"

NODE_NAME="${CFG[NODE_NAME]}"
ROLE="${CFG[CLUSTER_ROLE]}"
CAPACITY="${CFG[ADMISSION_CAPACITY_C]}"
CHURN_KUBECONFIG_FILE="${CFG[CHURN_KUBECONFIG_FILE]}"

[ -n "$NODE_NAME" ] || die "${PROFILE_ARG}: NODE_NAME is empty"
[[ "$CAPACITY" =~ ^[0-9]+$ ]] || die "${PROFILE_ARG}: ADMISSION_CAPACITY_C must be a non-negative integer, got '${CAPACITY}'"
case "$ROLE" in
  server) K3S_UNIT="k3s.service" ;;
  agent)  K3S_UNIT="k3s-agent.service" ;;
  *) die "${PROFILE_ARG}: CLUSTER_ROLE must be 'server' or 'agent', got '${ROLE}'" ;;
esac
if [ "$ROLE" = agent ]; then
  [ -n "$CHURN_KUBECONFIG_FILE" ] || die "${PROFILE_ARG}: CLUSTER_ROLE is 'agent' but CHURN_KUBECONFIG_FILE is empty -- an agent's reapply timer needs the node-status kubeconfig path (see ../node-status-credential/README.md)"
fi

# The installed profile copy the unit's ExecStart names.
INSTALLED_PROFILE="${LIB_DIR}/$(basename "$PROFILE_ARG")"

# ---------------------------------------------------------------------------
# ONE call site per command, printed as a '+ ' line and executed unless this is
# a dry run, so the sequence a dry run prints cannot describe a different run
# from the one that happens.
# ---------------------------------------------------------------------------
run() {  # run CMD ARG...
  printf '+ %s\n' "$*"
  [ "$DRY_RUN" -eq 1 ] || "$@"
}

if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
fi

# ---------------------------------------------------------------------------
log "1. Install the patch script and this node's profile to ${LIB_DIR}"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/patch-node-churn-capacity.sh" "${LIB_DIR}/patch-node-churn-capacity.sh"
run install -m 0644 "${PROFILE_ARG}" "${INSTALLED_PROFILE}"

# ---------------------------------------------------------------------------
log "2. Install the unit files, substituting k3s unit=${K3S_UNIT} and profile=${INSTALLED_PROFILE}"
# The substitution is the one step with a redirect, so it is printed rather than
# routed through `run`; the `sed` below and the line printed here are the same
# command written twice, on purpose, and neither is reachable in the other's mode.
if [ "$DRY_RUN" -eq 1 ]; then
  printf '+ sed -e s|K3S_UNIT_PLACEHOLDER|%s|g -e s|PROFILE_PATH_PLACEHOLDER|%s|g %s > %s\n' \
    "${K3S_UNIT}" "${INSTALLED_PROFILE}" "${SCRIPT_DIR}/${SERVICE}" "${UNIT_DIR}/${SERVICE}"
else
  sed -e "s|K3S_UNIT_PLACEHOLDER|${K3S_UNIT}|g" -e "s|PROFILE_PATH_PLACEHOLDER|${INSTALLED_PROFILE}|g" \
    "${SCRIPT_DIR}/${SERVICE}" > "${UNIT_DIR}/${SERVICE}"
  chmod 0644 "${UNIT_DIR}/${SERVICE}"
  # Fail loudly rather than installing a unit that would fail every five minutes.
  if grep -qE 'K3S_UNIT_PLACEHOLDER|PROFILE_PATH_PLACEHOLDER' "${UNIT_DIR}/${SERVICE}"; then
    die "a placeholder survived substitution in ${UNIT_DIR}/${SERVICE}"
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
# On an agent whose node-status kubeconfig is not seeded yet, the immediate
# service run would fail (the patch script has no credential). That is a
# PREREQUISITE this runbook cannot satisfy from here — the credential is seeded
# by the attended ../../secret-reinjection/seed-node-status-kubeconfig.sh — so the
# immediate run is SKIPPED with a warning rather than failing the install; the
# timer reconciles it once the credential lands. A server always holds its admin
# kubeconfig, so its verify is unconditional.
VERIFY_START=1
if [ "$ROLE" = agent ] && [ "$DRY_RUN" -eq 0 ] && [ ! -f "$CHURN_KUBECONFIG_FILE" ]; then
  VERIFY_START=0
  printf '  SKIP verify: %s is not present yet -- seed it with ../../secret-reinjection/seed-node-status-kubeconfig.sh, then: systemctl start %s\n' \
    "$CHURN_KUBECONFIG_FILE" "$SERVICE"
fi
if [ "$VERIFY_START" -eq 1 ]; then
  run systemctl start "${SERVICE}"
  run systemctl --no-pager status "${TIMER}" || true
  run kubectl get node "${NODE_NAME}" \
    -o jsonpath='{.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}'
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the sequence above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${TIMER} armed; ${SERVICE} reapplies ${NODE_NAME}'s capacity=${CAPACITY} at boot (before the converge) and every 5 minutes."
