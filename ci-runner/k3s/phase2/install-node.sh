#!/usr/bin/env bash
# install-node.sh — the ONE ordered runbook that takes a CI runner pool NODE
# from "k3s installed" to "every node-local mechanism in this tree installed
# and armed", so a from-scratch rebuild is one command rather than a list of
# installers run by hand in the right order.
#
# WHY THIS EXISTS: the reconstruct-on-boot path (reconstruct/ + the tmpfs
# datastore) rebuilds the CLUSTER from git on every boot, but it depends on a
# set of NODE-LOCAL installs — kernel sysctl, AppArmor profile, k3s config,
# systemd units and timers, /usr/local/lib copies — each with its own
# installer and each, until 2026-09-02, run by hand. A host is only cattle if
# the node-local half is as reproducible as the cluster half. This script
# encodes the order and the arguments (livespec plan
# `ci-runner-pod-lifecycle-reliability`, "CI host as reconstructible cattle").
#
# ROLE-AWARE (2026-09-06, livespec-dev-tooling-2ww4e7, livespec plan
# `k3s-on-gmktec-for-vps-usage` carrier R3). Until now this was written for the
# fleet's ONE node, which is the k3s SERVER: several steps reach the cluster
# through the admin kubeconfig, and one mounts the server datastore. A node
# that joins as an AGENT has neither, and it must still be brought up by THIS
# runbook rather than by a second copy of it. So the step plan is selected by
# the node's `CLUSTER_ROLE`, read from the per-node profile
# (`../phase0-bare-metal/profiles/<node>.env`), and every step is logged with
# that role — a step this role skips is logged with the REASON it skipped.
# `server` runs the same steps, in the same order, that it ran before this
# change; the "N/10" numbering below is that historical server numbering, kept
# verbatim so the two plans are comparable line by line.
#
# A SKIP ALSO CLEANS UP (2026-09-07, livespec-dev-tooling-43sc). Skipping a
# step is what this role's plan says about the FUTURE; it says nothing about
# what an EARLIER run of this runbook already put on the node. The runs that
# preceded the skips installed the server-only units on gmktec-xubuntu, and
# because those installers' own removal is reached only by INVOKING them —
# which a skip by definition does not do — a full, exit-0 run of this runbook
# left reapply-node-extended-resource.timer, scan-wedged-runners.timer and
# scan-runner-pod-lifecycle.timer `enabled` and `failed` with `Unit k3s.service
# not found`. So each agent-skipped step that installs units names them in
# STEP_STALE_UNITS below, and the run hands the lot to
# ./remove-server-only-units.sh: disabled, deleted, one daemon-reload, then one
# `reset-failed` per unit removed, printed as `+ ` lines under --dry-run and
# executed live. Idempotent — a node with none of them, and none of them
# failed, says so and does nothing. The reset-failed pass is not cosmetic:
# without it the deleted units stay in `systemctl list-units --state=failed` as
# `not-found failed` until the host reboots, which is what the next stage-4
# re-run found on that same node (2026-09-07, livespec-dev-tooling-oc5g).
#
# AND THE CLEAR IS OVER THE UNITS NAMED, not the units this run removed. The
# residual on that node was left by the run BEFORE the reset-failed pass
# existed, so by the time the pass shipped there was nothing left to remove and
# therefore nothing it would clear: the next re-run printed `nothing to remove`
# while the same three timers were still listed failed (2026-09-07,
# livespec-dev-tooling-ssbg). So each named unit the node does NOT carry is
# asked `systemctl is-failed` — a read, performed under --dry-run too — and
# cleared when the answer is `failed`.
#
# WHERE "Kueue" AND "ARC" LIVE IN THE AGENT SKIP SET. Neither is a step of
# this runbook on its own: the ONLY step that applies Kueue ClusterQueues and
# ARC scale sets is 8/10, the reconstruct-on-boot converge
# (reconstruct/converge-ci-stack.sh), so skipping 8 is exactly what omits them
# from an agent's plan. 6/10 "ARC log archive" is NOT that, and it is not
# node-local either: it archives the ARC CONTROLLER and LISTENER pods' logs
# through the admin kubeconfig, which is one pool-wide duty the server holds
# (see its skip reason below).
#
# ORDER, and why:
#   1. k3s-config          — read by k3s at start; sets max-pods on BOTH roles
#                            and, on a server only, disables the bundled
#                            provisioner. Before anything that needs the
#                            cluster, and before provision-k3s.sh on a truly
#                            fresh SERVER (that script calls it too, and skips
#                            it on an agent). The step is on both plans; the
#                            FILE it installs is what differs — config.yaml on a
#                            server, config.agent.yaml on an agent — because
#                            `disable`, `write-kubeconfig-mode` and `tls-san`
#                            are server-only keys and k3s-agent exits `flag
#                            provided but not defined: -disable` at the next
#                            start after being handed them
#                            (livespec-dev-tooling-vcv4).
#   2. node-inotify-budget, node-keyring-budget — kernel sysctls; no cluster
#                            needed. Then storage-layout — the five LABEL-keyed
#                            fstab lines (cache + two tiers + two binds) and
#                            the k3s RequiresMountsFor drop-in (a no-op on a
#                            live host; on a fresh one, format the three
#                            volumes with their role labels and mount the
#                            cache volume BEFORE k3s, see its header).
#                            Then host-thermal — racadm plus the iDRAC cooling
#                            settings (fan loop automatic, third-party PCIe
#                            response off, "Minimum Power" profile); iDRAC
#                            state, no cluster needed, not on the k3s chain.
#   3. apparmor            — kernel profile + the hook ConfigMap (needs API).
#   4. node-extended-resource CAPACITY — the churn-slot resource + its timer.
#                            SERVER only: the unit is ordered against
#                            k3s.service, patches node status with the admin
#                            kubeconfig, and patches EVERY labeled node with one
#                            capacity, so it is a cluster-wide act rather than a
#                            node-local one (see its skip reason below).
#   5. wedged-runner MODE  — the 5-minute wedge sweep, and 5b the runner-pod
#                            lifecycle sweep. SERVER only, both: each unit is
#                            ordered against k3s.service, each carries the admin
#                            kubeconfig, and each sweeps the pool's pods
#                            CLUSTER-WIDE, so the server's own timers already
#                            cover every node (see their skip reasons below).
#   6. arc-log-archive     — the log archive timer. SERVER only: it reads the
#                            ARC controller's and listeners' logs with that same
#                            admin kubeconfig, and those pods run on the server.
#   7. ../secret-reinjection — the boot-time secret unit (enabled, not run;
#                            credstore seeding is the SEPARATE attended step
#                            seed-github-app-creds.sh).
#   8. reconstruct         — the converge unit + every artifact it applies.
#   9. datastore-tmpfs     — pre-gates on 7 and 8 being enabled.
#  10. storage-sweep       — pre-gates on 9 being enabled ON A SERVER; an agent
#                            has no datastore to gate on, and its unit is
#                            ordered against k3s-agent.service instead. It is
#                            passed this run's PROFILE so it resolves that
#                            itself.
# The host OTel collector is installed from ITS OWN repository
# (thewoolleyman/otel-collector, scripts/install-ci-runner-host.sh) and the
# heartbeat/probe/gauge timers from ../../observability/install-observability.sh
# — the liveness heartbeat, the Kueue-webhook probe, the build-cache gauges and
# the per-repository pool gauges (ci-pool-attributed-gauges.*, livespec-i4ahv4);
# both are node-local too but live outside this tree, so they are listed here
# and not run. The pool gauges are a SERVER-node unit for the same reason steps
# 4, 5, 5b and 6 are: they read cluster-scoped ClusterQueues and an
# all-namespace EphemeralRunner listing through the admin kubeconfig an agent
# does not hold, and the server's own tick already covers every node.
#
# Every installer is idempotent, so this whole script is: re-run it after any
# edit to this tree to refresh the live copies (the recreatability rule).
# Nothing here starts the converge, mounts the tmpfs, or restarts k3s — those
# are boot events or attended steps, and this script says so at the end.
#
# CAPACITY COMES FROM THE PROFILE, not from the command line (the choice this
# work-item asked to be stated). `ADMISSION_CAPACITY_C` is already a required
# profile key, the profile is already this procedure's one place for a value
# that belongs to one node (SPECIFICATION/non-functional-requirements.md
# §"Runner-pool node rebuild recipe", "One profile per node"), and the README's
# standing warning — "pass the value the ten ClusterQueue quotas sum to, never
# a stale literal" — is satisfied by construction once the number is read
# rather than typed.
#
# --dry-run PRINTS THE PLAN AND EXECUTES NOTHING: no installer is invoked, no
# root check is made, no kubeconfig is required. That is what makes the two
# role plans assertable off-host (./install-node-exit-tests.sh). The stale-unit
# removal above prints under --dry-run too, and to print the sequence THIS host
# needs it performs the presence PROBE — `systemctl list-unit-files`, a read.
# That is the only command a dry run reaches, and it mutates nothing.
#
# Usage: install-node.sh --dry-run PROFILE [WEDGE_MODE]
#        sudo install-node.sh PROFILE [WEDGE_MODE]
#   PROFILE    path to the node's ../phase0-bare-metal/profiles/<node>.env;
#              this script reads NODE_NAME, CLUSTER_ROLE and
#              ADMISSION_CAPACITY_C from it
#   WEDGE_MODE 'report' or 'clear' for the wedged-runner scan (default clear,
#              the live choice on a host with no failure routing)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SCRIPT_NAME="$(basename "$0")"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] PROFILE [WEDGE_MODE]   (PROFILE = ../phase0-bare-metal/profiles/<node>.env, which carries CLUSTER_ROLE and the churn-slot capacity C; WEDGE_MODE = report|clear, default clear)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n#### %s ####\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
PROFILE_PATH=""
WEDGE_MODE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    # No `--` end-of-options case on purpose: no option here takes a value, so
    # `--` would only be a way to silently swallow the arguments after it.
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      if [ -z "$PROFILE_PATH" ]; then
        PROFILE_PATH="$1"
      elif [ -z "$WEDGE_MODE" ]; then
        WEDGE_MODE="$1"
      else
        die "unexpected extra argument '$1' -- ${USAGE}"
      fi ;;
  esac
  shift
done

[ -n "$PROFILE_PATH" ] || die "no profile given -- ${USAGE}"
WEDGE_MODE="${WEDGE_MODE:-clear}"
case "$WEDGE_MODE" in
  report|clear) ;;
  *) die "WEDGE_MODE must be report or clear, got '${WEDGE_MODE}'" ;;
esac

# ---------------------------------------------------------------------------
# Profile: parsed, never sourced
#
# The format is the one ../phase0-bare-metal/profiles/<node>.env documents in
# its own header: `KEY=value`, one per line, `#` comments and blank lines
# ignored, no quoting and no `$` expansion. Parsing rather than sourcing means
# a profile cannot smuggle in procedure.
#
# ONLY the keys this runbook consumes are required here. The WHOLE-file
# validation (every key present, the record grammar of the list-valued keys,
# the filesystem label limits) belongs to ../phase0-bare-metal/storage-layout.sh,
# the stage that consumes all of them; duplicating it here would be a second
# copy of a validator to drift.
# ---------------------------------------------------------------------------
[ -f "$PROFILE_PATH" ] || die "profile not found: ${PROFILE_PATH}"

CONSUMED_KEYS=(NODE_NAME CLUSTER_ROLE ADMISSION_CAPACITY_C)
declare -A CFG=()
profile_lineno=0
while IFS= read -r profile_line || [ -n "$profile_line" ]; do
  profile_lineno=$((profile_lineno + 1))
  case "$profile_line" in ''|'#'*) continue ;; esac
  case "$profile_line" in
    *=*) ;;
    *) die "${PROFILE_PATH}:${profile_lineno}: not a KEY=value line: ${profile_line}" ;;
  esac
  profile_key="${profile_line%%=*}"
  if ! [[ "$profile_key" =~ ^[A-Z][A-Z0-9_]*$ ]]; then
    die "${PROFILE_PATH}:${profile_lineno}: '${profile_key}' is not a profile key (want ^[A-Z][A-Z0-9_]*\$)"
  fi
  if [ -n "${CFG[$profile_key]+set}" ]; then
    die "${PROFILE_PATH}:${profile_lineno}: profile key '${profile_key}' given more than once"
  fi
  CFG["$profile_key"]="${profile_line#*=}"
done < "$PROFILE_PATH"

for profile_key in "${CONSUMED_KEYS[@]}"; do
  if [ -z "${CFG[$profile_key]+set}" ]; then
    die "${PROFILE_PATH}: missing required profile key '${profile_key}'"
  fi
  if [ -z "${CFG[$profile_key]}" ]; then
    die "${PROFILE_PATH}: profile key '${profile_key}' must not be empty"
  fi
done

NODE_NAME="${CFG[NODE_NAME]}"
ROLE="${CFG[CLUSTER_ROLE]}"
CAPACITY="${CFG[ADMISSION_CAPACITY_C]}"

case "$ROLE" in
  server|agent) ;;
  *) die "${PROFILE_PATH}: CLUSTER_ROLE must be 'server' or 'agent', got '${ROLE}'" ;;
esac
[[ "$CAPACITY" =~ ^[0-9]+$ ]] || die "${PROFILE_PATH}: ADMISSION_CAPACITY_C must be a non-negative integer, got '${CAPACITY}'"

# ---------------------------------------------------------------------------
# The step plan — ONE table, read by both --dry-run and the executor, so the
# printed plan can never describe a different run from the one that happens.
#
# STEP_SKIP[id] set  => the AGENT role skips that step, and the reason is
#                       logged in its place. An unset entry runs on both roles.
# STEP_SERVER_SKIP   => the mirror image: the SERVER role skips that step and
#                       logs the reason. The single entry is the agent-only
#                       rejoin watchdog, which the self-authoritative server
#                       never needs. A step is in at most one of the two maps.
# STEP_AGENT_LABEL   => the step runs on both roles but does something smaller
#                       on an agent, and says so.
# STEP_AGENT_NOTE    => the step runs on an agent and carries a caveat the
#                       operator has to see (a prerequisite this runbook
#                       cannot satisfy from here). No step carries one today:
#                       the churn-slot caveat that used to be the only entry
#                       became a SKIP reason in livespec-dev-tooling-ukbp, the
#                       step having turned out to be server-only in kind.
# ---------------------------------------------------------------------------
STEP_IDS=(
  k3s-config
  agent-rejoin
  kernel-budgets
  storage-layout
  host-thermal
  host-tools
  apparmor
  churn-slot
  wedged-runner
  runner-pod-lifecycle
  arc-log-archive
  secret-reinjection
  sccache
  container-hook
  reconstruct
  datastore-tmpfs
  storage-sweep
)

declare -A STEP_LABEL=()
declare -A STEP_AGENT_LABEL=()
declare -A STEP_AGENT_NOTE=()
declare -A STEP_SKIP=()
declare -A STEP_SERVER_SKIP=()

STEP_LABEL[k3s-config]="1/10 k3s config (server or agent) — installs k3s-config/config.yaml + the local-storage skip marker"
STEP_LABEL[agent-rejoin]="1b/10 agent-rejoin liveness watchdog (agent only) — restarts a wedged k3s-agent so it re-registers after a control-plane datastore wipe"
STEP_LABEL[kernel-budgets]="2/10 inotify instance budget + keyring quota"
STEP_LABEL[storage-layout]="2b/10 storage layout (mount the LABEL-ed tiers + the five fstab lines + k3s drop-in; no-op when the tiers are live)"
STEP_LABEL[host-thermal]="2c/10 iDRAC cooling configuration (racadm + fan loop automatic, third-party response off, Minimum Power profile)"
STEP_LABEL[host-tools]="2d/10 operator host tools (btop-loop into /usr/local/bin)"
STEP_LABEL[apparmor]="3/10 AppArmor profile + hook ConfigMap"
STEP_LABEL[churn-slot]="4/10 churn-slot extended resource (capacity ${CAPACITY}) + reapply timer"
STEP_LABEL[wedged-runner]="5/10 wedged-runner scan (${WEDGE_MODE})"
STEP_LABEL[runner-pod-lifecycle]="5b/10 runner-pod lifecycle scan (report-only; no mode — see its installer's header)"
STEP_LABEL[arc-log-archive]="6/10 ARC log archive"
STEP_LABEL[secret-reinjection]="7/10 boot-time secret reinjection units — GitHub App + gate forge credential (enable only)"
STEP_LABEL[sccache]="7b/10 pool-provided sccache binary (node-local; mounted read-only into every job)"
STEP_LABEL[container-hook]="7c/10 fleet-patched ARC container hook + externals extraction from the pinned runner image"
STEP_LABEL[reconstruct]="8/10 reconstruct-on-boot converge unit + artifacts (enable only)"
STEP_LABEL[datastore-tmpfs]="9/10 tmpfs datastore mount (enable only, never started here)"
STEP_LABEL[storage-sweep]="10/10 boot-time orphaned-scratch sweep (enable only)"

# The two steps whose WORK differs by role rather than their presence. Each
# label names the ARTEFACT that differs, so a --dry-run plan says which file the
# step installs rather than only that the step runs.
#
# k3s-config: max-pods is node state both roles need, while `disable`,
# `write-kubeconfig-mode` and `tls-san` are server-only keys — an agent handed
# them does not ignore them, it exits `flag provided but not defined: -disable`
# at the next k3s start and restart-loops (gmktec-xubuntu 2026-09-07,
# livespec-dev-tooling-vcv4). The skip marker's directory,
# /var/lib/rancher/k3s/server/manifests/, is a SERVER path for the same reason.
# The agent label also names the WAIT that step earns the rest of this runbook:
# the same host, hours later, ran this step against a restart-looping
# k3s-agent.service and then reached 7c five seconds before containerd was
# serving, so extract-externals.sh died at its first `ctr images pull` with
# `connect: connection refused` and the whole runbook had to be invoked twice
# (livespec-dev-tooling-4qp4). A server has no such window — provision-k3s.sh
# waits for the node to go Ready before the runbook and no server step restarts
# k3s — so its label and its behaviour are unchanged.
STEP_AGENT_LABEL[k3s-config]="1/10 k3s config (server or agent) — installs k3s-config/config.agent.yaml and NO local-storage skip marker (both are server-only); a CHANGED config with k3s-agent.service active or activating is then followed by a bounded wait for that unit to be active and for the containerd socket /run/k3s/containerd/containerd.sock, restarting nothing"
# apparmor: the kernel profile is node state and an agent needs it, while the
# arc-hook-pod-template ConfigMap the same installer converges is a cluster
# object.
STEP_AGENT_LABEL[apparmor]="3/10 AppArmor profile only (--profile-only; the hook ConfigMap is a cluster object the server converges)"

STEP_SKIP[host-thermal]="iDRAC state reached through Dell's racadm packages — PowerEdge hardware, and the pool's PowerEdge is its server. This is the one skip that uses the role as a PROXY for the hardware; if a PowerEdge ever joins as an agent this becomes its own profile key, not a role test."
STEP_SKIP[secret-reinjection]="writes the GitHub App Secret and the gate forge-credential Secret into the cluster at boot — cluster-scoped objects, applied with the admin kubeconfig an agent does not hold, owned by the node that holds the datastore."
STEP_SKIP[reconstruct]="rebuilds the CLUSTER from git at boot — the fleet-owned provisioner, Kueue and every ClusterQueue, the ARC controller and every scale set. Cluster-scoped, admin-kubeconfig-only, and the server's job; this is the step whose absence omits Kueue and ARC from an agent's plan."
STEP_SKIP[datastore-tmpfs]="mounts the k3s SERVER datastore on tmpfs; an agent node has no datastore to mount."
STEP_SKIP[wedged-runner]="sweeps the ARC runner pods CLUSTER-WIDE from a unit ordered Requires=k3s.service (an agent runs k3s-agent.service, so it cannot start at all) with the admin kubeconfig an agent does not hold. The SERVER's own scan-wedged-runners.timer already performs that sweep every five minutes over every pod on every node, this one included (livespec-dev-tooling-qcq0)."
STEP_SKIP[runner-pod-lifecycle]="reads PVCs, scheduler events, scale-set listeners and node capacity CLUSTER-WIDE from a unit ordered Requires=k3s.service (an agent runs k3s-agent.service) with the admin kubeconfig an agent does not hold. The SERVER's own scan-runner-pod-lifecycle.timer already performs that diagnosis every five minutes for the whole pool, this node included (livespec-dev-tooling-qcq0)."
STEP_SKIP[arc-log-archive]="archives the ARC CONTROLLER and LISTENER pods' logs with the admin kubeconfig an agent does not hold — pods that run on the SERVER for the whole pool, so there is nothing here to archive. Unlike the two scans this unit is ordered After=network-online.target, so on an agent it would install cleanly and then fail silently every two minutes; the SERVER's own archive-arc-logs.timer already covers every node (livespec-dev-tooling-qcq0)."
STEP_SKIP[churn-slot]="patches node STATUS through the API from a unit ordered Requires=k3s.service (an agent runs k3s-agent.service) with the admin kubeconfig an agent does not hold — and patch-node-churn-capacity.sh patches EVERY node labeled k3s-role=arc-runner-host with ONE capacity, which makes applying it a cluster-wide act rather than a node-local one. Node-status patches are therefore applied from the SERVER's reapply timer, whose selector already includes this node; a per-node capacity read from each node's own profile is R4/R5 scope (livespec-dev-tooling-xa6o)."

# The one SERVER skip, the mirror of the agent skips above: the rejoin watchdog
# restarts a wedged k3s-AGENT so it re-registers after the control-plane
# datastore (a tmpfs, empty at every boot) drops its Node object. The SERVER
# holds that datastore and never loses its OWN registration; it runs k3s.service
# not k3s-agent.service, so the watchdog's first gate is never true there; and it
# would gain only a timer firing into a condition that cannot arise. So it is
# server-skipped, and install-agent-rejoin-watchdog.sh refuses on a server too —
# the same two-belt guard the four server-only steps use in the other direction.
STEP_SERVER_SKIP[agent-rejoin]="the rejoin watchdog restarts a wedged k3s-AGENT so it re-registers after a control-plane datastore wipe. This node is the self-authoritative SERVER: it holds the datastore, never loses its own registration, and runs k3s.service not k3s-agent.service, so the watchdog's alive-but-wedged condition cannot arise here. The watchdog belongs on the AGENTS this server serves."

# ---------------------------------------------------------------------------
# The units a SKIPPED step would have installed, and which an earlier run of
# this runbook — one made before that step learned to skip — therefore left on
# the node. The TIMER is listed before the service it triggers, so nothing can
# fire between the two removals.
#
# Only the four unit-installing steps whose installers have been established as
# server-only carry an entry (livespec-dev-tooling-ukbp for step 4,
# livespec-dev-tooling-qcq0 for 5, 5b and 6). The other four agent skips are
# deliberately absent: 2c installs no unit on this path, and 7, 8 and 9 belong
# to installers that do not yet know about roles at all — declaring their units
# server-only HERE would assert something no installer has been changed to
# state, and this table is not the place to decide it. On gmktec-xubuntu those
# three never ran on an agent anyway: the runbook aborted at step 4 of 10.
# ---------------------------------------------------------------------------
declare -A STEP_STALE_UNITS=()
STEP_STALE_UNITS[churn-slot]="reapply-node-extended-resource.timer reapply-node-extended-resource.service"
STEP_STALE_UNITS[wedged-runner]="scan-wedged-runners.timer scan-wedged-runners.service"
STEP_STALE_UNITS[runner-pod-lifecycle]="scan-runner-pod-lifecycle.timer scan-runner-pod-lifecycle.service"
STEP_STALE_UNITS[arc-log-archive]="archive-arc-logs.timer archive-arc-logs.service"

step_label() {  # step_label ID
  if [ "$ROLE" = agent ] && [ -n "${STEP_AGENT_LABEL[$1]:-}" ]; then
    printf '%s' "${STEP_AGENT_LABEL[$1]}"
  else
    printf '%s' "${STEP_LABEL[$1]}"
  fi
}

step_skipped() {  # step_skipped ID -> true when THIS role skips it
  if [ "$ROLE" = agent ]; then
    [ -n "${STEP_SKIP[$1]:-}" ]
  else
    [ -n "${STEP_SERVER_SKIP[$1]:-}" ]
  fi
}

# The skip REASON for whichever role skips this step, so print_plan reads one
# map without knowing which side owns the entry.
step_skip_reason() {  # step_skip_reason ID
  if [ "$ROLE" = agent ]; then
    printf '%s' "${STEP_SKIP[$1]:-}"
  else
    printf '%s' "${STEP_SERVER_SKIP[$1]:-}"
  fi
}

print_plan() {
  local id
  printf '== %s step plan ==\n' "$SCRIPT_NAME"
  printf 'profile:  %s\n' "$PROFILE_PATH"
  printf 'node:     %s\n' "$NODE_NAME"
  printf 'role:     %s\n' "$ROLE"
  printf 'capacity: %s (ADMISSION_CAPACITY_C)\n' "$CAPACITY"
  printf 'wedge:    %s\n' "$WEDGE_MODE"
  printf '\n'
  for id in "${STEP_IDS[@]}"; do
    if step_skipped "$id"; then
      printf 'SKIP [%s] %s\n' "$ROLE" "${STEP_LABEL[$id]}"
      printf '     reason: %s\n' "$(step_skip_reason "$id")"
      continue
    fi
    printf 'RUN  [%s] %s\n' "$ROLE" "$(step_label "$id")"
    if [ "$ROLE" = agent ] && [ -n "${STEP_AGENT_NOTE[$id]:-}" ]; then
      printf '     note: %s\n' "${STEP_AGENT_NOTE[$id]}"
    fi
  done
}

# ONE phase rather than a removal inside each skipped step, for two reasons:
# the whole set is cleared with a SINGLE daemon-reload, and the sequence a
# --dry-run prints is then the same sequence a live run performs, in the same
# place — the property the rest of this script is built around. A role that
# skips nothing (a server) invokes nothing and prints nothing.
remove_stale_server_only_units() {
  local id units=() step_units=()
  for id in "${STEP_IDS[@]}"; do
    step_skipped "$id" || continue
    [ -n "${STEP_STALE_UNITS[$id]:-}" ] || continue
    read -r -a step_units <<< "${STEP_STALE_UNITS[$id]}"
    units+=("${step_units[@]}")
  done
  [ "${#units[@]}" -gt 0 ] || return 0
  log "[${ROLE}] REMOVE the server-only units the skipped steps install — an earlier run of this runbook could have left them here, and a host carrying a unit it cannot run is drift"
  if [ "$DRY_RUN" -eq 1 ]; then
    "${SCRIPT_DIR}/remove-server-only-units.sh" --dry-run "${units[@]}"
  else
    "${SCRIPT_DIR}/remove-server-only-units.sh" "${units[@]}"
  fi
}

run_step() {  # run_step ID
  case "$1" in
    # Passed this run's ROLE because the FILE it installs is role-dependent:
    # the server config on an agent is fatal to k3s-agent at its next start
    # (livespec-dev-tooling-vcv4), and the installer also removes the
    # server-path skip marker an earlier run left on an agent. The role also
    # selects whether the installer WAITS afterwards: on an agent whose config
    # it changed while k3s-agent.service was up or coming up, it blocks until
    # the unit is active and containerd answers, so every step after this one
    # meets one runtime rather than a restarting one
    # (livespec-dev-tooling-4qp4).
    k3s-config)
      "${SCRIPT_DIR}/k3s-config/install-k3s-config.sh" --role "${ROLE}" ;;
    # Agent-only (server-skipped above), and passed this run's ROLE for the same
    # two-belt reason the server-only installers are: the installer refuses on a
    # server (removing any copy it finds), so if a future edit ever drops the
    # STEP_SERVER_SKIP entry, this step fails loudly at the installer's own
    # refusal rather than arming an agent watchdog on a server.
    agent-rejoin)
      "${SCRIPT_DIR}/agent-rejoin/install-agent-rejoin-watchdog.sh" --role "${ROLE}" ;;
    kernel-budgets)
      "${SCRIPT_DIR}/node-inotify-budget/install-inotify-sysctl.sh"
      "${SCRIPT_DIR}/node-keyring-budget/install-keyring-sysctl.sh" ;;
    storage-layout)
      "${SCRIPT_DIR}/storage-layout/install-storage-layout.sh" ;;
    host-thermal)
      "${SCRIPT_DIR}/host-thermal/install-host-thermal.sh" ;;
    host-tools)
      "${SCRIPT_DIR}/host-tools/install-host-tools.sh" ;;
    apparmor)
      if [ "$ROLE" = agent ]; then
        "${SCRIPT_DIR}/apparmor/install-apparmor-profile.sh" --profile-only
      else
        "${SCRIPT_DIR}/apparmor/install-apparmor-profile.sh"
      fi ;;
    # The four server-only unit installers are passed this run's ROLE even
    # though only a server reaches these lines: each refuses on an agent (and
    # removes any copy it finds), so if a future edit ever drops one of the
    # skips above, that step fails loudly at the installer's own refusal rather
    # than halfway through installing a unit that cannot run. That is the
    # failure gmktec paid for twice: step 4 and then step 5b each aborted the
    # whole runbook at their own verify, and step 5 did something worse — it
    # installed a timer that landed `failed` and reported DONE over it
    # (livespec-dev-tooling-ukbp, livespec-dev-tooling-qcq0).
    churn-slot)
      "${SCRIPT_DIR}/node-extended-resource/install-reapply-unit.sh" --role "${ROLE}" "${CAPACITY}" ;;
    wedged-runner)
      "${SCRIPT_DIR}/wedged-runner/install-wedged-runner-scan.sh" --role "${ROLE}" "${WEDGE_MODE}" ;;
    runner-pod-lifecycle)
      "${SCRIPT_DIR}/runner-pod-lifecycle/install-runner-pod-lifecycle-scan.sh" --role "${ROLE}" ;;
    arc-log-archive)
      "${SCRIPT_DIR}/arc-log-archive/install-arc-log-archive.sh" --role "${ROLE}" ;;
    secret-reinjection)
      "${K3S_DIR}/secret-reinjection/install-secret-reinjection-unit.sh" ;;
    sccache)
      "${SCRIPT_DIR}/sccache/install-sccache-binary.sh"
      "${SCRIPT_DIR}/cache-telemetry/install-cache-telemetry.sh" ;;
    # 7c: the fleet-patched ARC container hook (built on a developer host,
    # committed under container-hook/bundle/<runner-version>/) to
    # /usr/local/lib/ci-runner-k3s/hooks/<runner-version>/, plus the pinned
    # image's externals extracted beside the work volumes for the provisioner's
    # hardlink seed. Before 8 because the values files the boot converge applies
    # select the hook by that path (livespec-wm7c; container-hook/README.md).
    # Mounts the image through containerd, so k3s must be running.
    container-hook)
      "${SCRIPT_DIR}/container-hook/install-container-hook.sh" ;;
    reconstruct)
      "${SCRIPT_DIR}/reconstruct/install-converge-unit.sh" ;;
    datastore-tmpfs)
      "${SCRIPT_DIR}/datastore-tmpfs/install-datastore-tmpfs.sh" ;;
    # The one step handed this run's PROFILE rather than a flag: it resolves
    # the node's CLUSTER_ROLE out of it, because the pre-gate it applies and
    # the k3s unit its own unit is ordered against are both role-dependent
    # (livespec-dev-tooling-92wn).
    storage-sweep)
      "${SCRIPT_DIR}/storage-sweep/install-storage-sweep.sh" "${PROFILE_PATH}" ;;
    *)
      die "no runner for step '$1' (the step table and run_step have drifted)" ;;
  esac
}

# ---------------------------------------------------------------------------
# --dry-run stops here, having touched nothing at all.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  print_plan
  remove_stale_server_only_units
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

# ---------------------------------------------------------------------------
# Preconditions, by role. The admin kubeconfig is a SERVER precondition: it is
# what the cluster-side steps use, and those are exactly the steps an agent
# skips. Demanding it on an agent would make this runbook unusable on the very
# node it was made role-aware for.
# ---------------------------------------------------------------------------
[ "$(id -u)" -eq 0 ] || die "must run as root"
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"
if [ "$ROLE" = server ]; then
  [ -f "$KUBECONFIG" ] || die "${KUBECONFIG} not found — run ../provision-k3s.sh first"
fi

print_plan
remove_stale_server_only_units

for step_id in "${STEP_IDS[@]}"; do
  if step_skipped "$step_id"; then
    log "[${ROLE}] SKIP ${STEP_LABEL[$step_id]} — ${STEP_SKIP[$step_id]}"
    continue
  fi
  log "[${ROLE}] $(step_label "$step_id")"
  run_step "$step_id"
done

log "[${ROLE}] DONE — node-local mechanisms installed and armed"
cat <<'EOF'
Not done here, by design:
  - credstore seeding (attended, once): ../secret-reinjection/seed-github-app-creds.sh
  - the host OTel collector: thewoolleyman/otel-collector scripts/install-ci-runner-host.sh
  - the heartbeat, Kueue-webhook probe, build-cache gauge and per-repository
    pool gauge timers: ../../observability/install-observability.sh
    (the pool gauges read the cluster through the admin kubeconfig, so they
     belong to a SERVER node — see this script's header)
  - the warm-cache initial populate (attended): warm-cache/install-warm-cache.sh
  - a k3s restart or reboot: config.yaml changes and the tmpfs cutover take
    effect on the next k3s start; do that at zero active CI jobs, or reboot —
    the reconstruct units then rebuild the cluster from these artifacts.
Verify a boot with the checklist in README.md "Reconstruct-on-boot".
EOF
