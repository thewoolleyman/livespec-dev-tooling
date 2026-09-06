#!/usr/bin/env bash
# install-storage-sweep.sh — install the boot-ordered orphaned-scratch sweep
# on a k3s runner NODE: the script into /usr/local/lib/ci-runner-k3s/ and the
# oneshot unit into /etc/systemd/system, ENABLED for next boot and never
# started here.
#
# WHY NEVER --now: the sweep removes every local-path volume directory and is
# safe ONLY before the node's k3s unit on an empty-datastore boot (see the unit
# and script headers). Starting it under a running k3s is refused by the script,
# but the installer does not try. The sweep runs on the next boot.
#
# ROLE-AWARE (2026-09-06, livespec-dev-tooling-92wn, livespec plan
# `k3s-on-gmktec-for-vps-usage` carrier R3 follow-up). Until now this was
# written for the fleet's ONE node, which is the k3s SERVER, and it REFUSED on
# an agent for two reasons that were both really the same one — it had no way
# to know the node's role. It pre-gated on the tmpfs datastore mount an agent
# does not have, and it installed a unit ordered against `k3s.service`, which is
# not the name of the k3s unit an agent runs. Both now read the role:
#
#   server  the pre-gate below applies, the base unit is installed alone, and
#           the command sequence is the one this script ran before this change.
#   agent   the pre-gate is SKIPPED with its reason logged (an agent holds no
#           datastore, so there is no mount to gate on — ../datastore-tmpfs/ is
#           a step the runbook skips on this role), and ./agent-ordering.conf is
#           installed as a drop-in so the unit is ordered `Before=k3s-agent.service`.
#
# WHAT THIS DOES NOT DO: it never REMOVES the agent drop-in. A server run does
# not delete one left by an earlier agent run, because doing so would add a
# command to the server's sequence that the sequence never had, and a node
# whose role changes is a REBUILD — a new profile, a different k3s install, a
# different runbook — not a re-run of this installer. If a node's role is ever
# flipped in place, remove /etc/systemd/system/sweep-runner-scratch.service.d/
# by hand before re-running this.
#
# PRECONDITION, on a SERVER: this sweep only makes sense on a node whose
# datastore is volatile (../datastore-tmpfs/). It pre-gates on that mount unit
# being enabled and refuses otherwise — on a persistent-datastore node the
# condition never holds and the unit would be inert clutter. An agent has no
# datastore of either kind, so the pre-gate does not apply to it; what the
# agent's sweep is safe under is stated in ./sweep-runner-scratch.sh's header.
#
# NODE-LOCAL, like the sibling installers: re-run after any node rebuild.
# Requires: root, systemd. `--dry-run` requires neither and executes nothing.
#
# Usage: install-storage-sweep.sh [--dry-run] [--role server|agent] [PROFILE]
#   PROFILE  path to the node's ../../phase0-bare-metal/profiles/<node>.env,
#            read for its CLUSTER_ROLE and for NOTHING else. This is the form
#            ../install-node.sh passes, so the role a step installs for is the
#            role the profile declares rather than one typed at a call site.
#   --role   the same choice made explicitly, for a hand run with no profile to
#            point at. Give either a PROFILE or --role, never both.
#   Neither  defaults to `server`, which is what a bare invocation meant before
#            this script knew about roles.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "$0")"
LIB_DIR="/usr/local/lib/ci-runner-k3s"
UNIT_DIR="/etc/systemd/system"
SERVICE="sweep-runner-scratch.service"
MOUNT_UNIT="var-lib-rancher-k3s-server-db.mount"
SRC_UNIT="${SCRIPT_DIR}/${SERVICE}"
SRC_DROPIN="${SCRIPT_DIR}/agent-ordering.conf"
DROPIN_DIR="${UNIT_DIR}/${SERVICE}.d"
DROPIN="${DROPIN_DIR}/10-agent-ordering.conf"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--role server|agent] [PROFILE]   (PROFILE = ../../phase0-bare-metal/profiles/<node>.env, read for its CLUSTER_ROLE only)"

PREGATE_AGENT_REASON="an agent node holds no k3s datastore, so there is no ${MOUNT_UNIT} to gate on — ../datastore-tmpfs/ is a step ../install-node.sh skips on this role."

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
ROLE=""
ROLE_GIVEN=0
PROFILE_PATH=""

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
      [ -z "$PROFILE_PATH" ] || die "unexpected extra argument '$1' -- ${USAGE}"
      PROFILE_PATH="$1" ;;
  esac
  shift
done

if [ "$ROLE_GIVEN" -eq 1 ] && [ -n "$PROFILE_PATH" ]; then
  die "give either --role or a PROFILE, not both -- ${USAGE}"
fi

# The profile is PARSED and never sourced, and exactly ONE key is read out of
# it. This is deliberately NOT a second whole-file validator: ../install-node.sh
# validates the keys it consumes and ../../phase0-bare-metal/storage-layout.sh
# validates the whole file, and a third copy here would be a third thing to
# drift. A leaf installer needs the role and nothing else.
profile_role() {  # profile_role PATH -> the profile's CLUSTER_ROLE on stdout
  local path="$1" line seen=0 value=""
  [ -f "$path" ] || die "profile not found: ${path}"
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in CLUSTER_ROLE=*) ;; *) continue ;; esac
    [ "$seen" -eq 0 ] || die "${path}: profile key 'CLUSTER_ROLE' given more than once"
    seen=1
    value="${line#*=}"
  done < "$path"
  [ "$seen" -eq 1 ] || die "${path}: missing required profile key 'CLUSTER_ROLE'"
  [ -n "$value" ] || die "${path}: profile key 'CLUSTER_ROLE' must not be empty"
  printf '%s' "$value"
}

if [ -n "$PROFILE_PATH" ]; then
  # `|| exit 1` on purpose: `die` inside a command substitution exits the
  # SUBSHELL, so without this the assignment's failure would not stop the run.
  ROLE="$(profile_role "$PROFILE_PATH")" || exit 1
fi
ROLE="${ROLE:-server}"
case "$ROLE" in
  server|agent) ;;
  *) die "role must be 'server' or 'agent', got '${ROLE}'" ;;
esac

# ---------------------------------------------------------------------------
# ONE call site per command, printed under --dry-run and executed otherwise, so
# the plan a dry run prints cannot describe a different run from the one that
# happens.
# ---------------------------------------------------------------------------
run() {  # run CMD ARG...
  if [ "$DRY_RUN" -eq 1 ]; then
    printf '  %s\n' "$*"
  else
    "$@"
  fi
}

# The unit's EFFECTIVE ordering for the resolved role, DERIVED from the very
# files that get installed rather than restated here: the base unit, then (on an
# agent) the drop-in, replayed through systemd's own rule that an empty
# assignment RESETS the list that key has accumulated.
resolved_ordering() {
  local -a sources=("$SRC_UNIT") keys=()
  local -A values=()
  local source line key value
  # `if` and not `&&`: under `set -e` a bare `test && append` that tests false
  # is a failing command list, and would exit the script on a server.
  if [ "$ROLE" = agent ]; then
    sources+=("$SRC_DROPIN")
  fi
  for source in "${sources[@]}"; do
    while IFS= read -r line || [ -n "$line" ]; do
      case "$line" in
        Before=*|After=*|Requires=*|RequiresMountsFor=*) ;;
        *) continue ;;
      esac
      key="${line%%=*}"
      value="${line#*=}"
      [ -n "${values[$key]+set}" ] || keys+=("$key")
      if [ -z "$value" ]; then
        values["$key"]=""
      elif [ -z "${values[$key]:-}" ]; then
        values["$key"]="$value"
      else
        values["$key"]+=$'\n'"$value"
      fi
    done < "$source"
  done
  for key in "${keys[@]}"; do
    [ -n "${values[$key]}" ] || continue
    while IFS= read -r value; do
      printf '  %s=%s\n' "$key" "$value"
    done <<< "${values[$key]}"
  done
}

printf '== %s plan ==\n' "$SCRIPT_NAME"
printf 'role:    %s\n' "$ROLE"
printf 'unit:    %s\n' "$SERVICE"
printf '\nunit ordering (role-resolved):\n'
resolved_ordering

if [ "$DRY_RUN" -eq 0 ]; then
  [ "$(id -u)" -eq 0 ] || die "must run as root (writes ${LIB_DIR} and ${UNIT_DIR})"
  command -v systemctl >/dev/null || die "systemctl not found on PATH"
fi

# ---------------------------------------------------------------------------
log "0. Pre-gate: the tmpfs datastore mount must be enabled"
if [ "$ROLE" = agent ]; then
  printf '  SKIPPED [agent]: %s\n' "$PREGATE_AGENT_REASON"
elif ! run systemctl is-enabled --quiet "$MOUNT_UNIT"; then
  echo "FATAL: ${MOUNT_UNIT} is not enabled. The sweep is only meaningful on a volatile-datastore node"
  echo "       (../datastore-tmpfs/install-datastore-tmpfs.sh first)."
  exit 1
elif [ "$DRY_RUN" -eq 0 ]; then
  echo "${MOUNT_UNIT}: enabled — OK"
fi

# ---------------------------------------------------------------------------
log "1. Install the sweep script to ${LIB_DIR}"
run install -d -m 0755 "${LIB_DIR}"
run install -m 0755 "${SCRIPT_DIR}/sweep-runner-scratch.sh" "${LIB_DIR}/sweep-runner-scratch.sh"

# ---------------------------------------------------------------------------
log "2. Install the unit and enable it for next boot (NEVER --now)"
run install -m 0644 "${SRC_UNIT}" "${UNIT_DIR}/${SERVICE}"
if [ "$ROLE" = agent ]; then
  run install -d -m 0755 "${DROPIN_DIR}"
  run install -m 0644 "${SRC_DROPIN}" "${DROPIN}"
fi
run systemctl daemon-reload
run systemctl enable "${SERVICE}"

# ---------------------------------------------------------------------------
log "3. Verify enabled"
if [ "$DRY_RUN" -eq 1 ]; then
  run systemctl is-enabled "${SERVICE}"
else
  state="$(systemctl is-enabled "${SERVICE}" 2>/dev/null || true)"
  [ "$state" = "enabled" ] || die "${SERVICE} is '${state}', expected 'enabled'"
fi

if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

log "DONE. ${SERVICE} enabled; it sweeps orphaned runner scratch before k3s on the next empty-datastore boot."
