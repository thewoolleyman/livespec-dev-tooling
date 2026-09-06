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
# WHERE "Kueue" AND "ARC" LIVE IN THE AGENT SKIP SET. Neither is a step of
# this runbook on its own: the ONLY step that applies Kueue ClusterQueues and
# ARC scale sets is 8/10, the reconstruct-on-boot converge
# (reconstruct/converge-ci-stack.sh), so skipping 8 is exactly what omits them
# from an agent's plan. 6/10 "ARC log archive" is NOT that — it is a
# node-local systemd timer archiving the runner pods' logs off THIS node's
# disk, so it runs on both roles.
#
# ORDER, and why:
#   1. k3s-config          — read by k3s at start; disables the bundled
#                            provisioner, sets max-pods. Before anything that
#                            needs the cluster, and before provision-k3s.sh on
#                            a truly fresh host (that script calls it too).
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
#   5. wedged-runner MODE  — the 5-minute wedge sweep.
#   6. arc-log-archive     — the log archive timer.
#   7. ../secret-reinjection — the boot-time secret unit (enabled, not run;
#                            credstore seeding is the SEPARATE attended step
#                            seed-github-app-creds.sh).
#   8. reconstruct         — the converge unit + every artifact it applies.
#   9. datastore-tmpfs     — pre-gates on 7 and 8 being enabled.
#  10. storage-sweep       — pre-gates on 9 being enabled.
# The host OTel collector is installed from ITS OWN repository
# (thewoolleyman/otel-collector, scripts/install-ci-runner-host.sh) and the
# heartbeat/probe timers from ../../observability/install-observability.sh;
# both are node-local too but live outside this tree, so they are listed here
# and not run.
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
# role plans assertable off-host (./install-node-exit-tests.sh).
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
# STEP_AGENT_LABEL   => the step runs on both roles but does something smaller
#                       on an agent, and says so.
# STEP_AGENT_NOTE    => the step runs on an agent and carries a caveat the
#                       operator has to see (a prerequisite this runbook
#                       cannot satisfy from here).
# ---------------------------------------------------------------------------
STEP_IDS=(
  k3s-config
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

STEP_LABEL[k3s-config]="1/10 k3s server config"
STEP_LABEL[kernel-budgets]="2/10 inotify instance budget + keyring quota"
STEP_LABEL[storage-layout]="2b/10 storage layout (LABEL fstab lines + k3s drop-in; no-op when the tiers are live)"
STEP_LABEL[host-thermal]="2c/10 iDRAC cooling configuration (racadm + fan loop automatic, third-party response off, Minimum Power profile)"
STEP_LABEL[host-tools]="2d/10 operator host tools (btop-loop into /usr/local/bin)"
STEP_LABEL[apparmor]="3/10 AppArmor profile + hook ConfigMap"
STEP_LABEL[churn-slot]="4/10 churn-slot extended resource (capacity ${CAPACITY}) + reapply timer"
STEP_LABEL[wedged-runner]="5/10 wedged-runner scan (${WEDGE_MODE})"
STEP_LABEL[runner-pod-lifecycle]="5b/10 runner-pod lifecycle scan (report-only; no mode — see its installer's header)"
STEP_LABEL[arc-log-archive]="6/10 ARC log archive"
STEP_LABEL[secret-reinjection]="7/10 boot-time GitHub App secret reinjection unit (enable only)"
STEP_LABEL[sccache]="7b/10 pool-provided sccache binary (node-local; mounted read-only into every job)"
STEP_LABEL[container-hook]="7c/10 fleet-patched ARC container hook + externals extraction from the pinned runner image"
STEP_LABEL[reconstruct]="8/10 reconstruct-on-boot converge unit + artifacts (enable only)"
STEP_LABEL[datastore-tmpfs]="9/10 tmpfs datastore mount (enable only, never started here)"
STEP_LABEL[storage-sweep]="10/10 boot-time orphaned-scratch sweep (enable only)"

# The one step whose WORK differs by role rather than its presence: the kernel
# profile is node state and an agent needs it, while the arc-hook-pod-template
# ConfigMap the same installer converges is a cluster object.
STEP_AGENT_LABEL[apparmor]="3/10 AppArmor profile only (--profile-only; the hook ConfigMap is a cluster object the server converges)"

STEP_SKIP[host-thermal]="iDRAC state reached through Dell's racadm packages — PowerEdge hardware, and the pool's PowerEdge is its server. This is the one skip that uses the role as a PROXY for the hardware; if a PowerEdge ever joins as an agent this becomes its own profile key, not a role test."
STEP_SKIP[secret-reinjection]="writes the GitHub App Secret into the cluster at boot — one cluster-scoped object, applied with the admin kubeconfig an agent does not hold, owned by the node that holds the datastore."
STEP_SKIP[reconstruct]="rebuilds the CLUSTER from git at boot — the fleet-owned provisioner, Kueue and every ClusterQueue, the ARC controller and every scale set. Cluster-scoped, admin-kubeconfig-only, and the server's job; this is the step whose absence omits Kueue and ARC from an agent's plan."
STEP_SKIP[datastore-tmpfs]="mounts the k3s SERVER datastore on tmpfs; an agent node has no datastore to mount."

STEP_AGENT_NOTE[churn-slot]="the installed timer patches THIS node's status through the API, so an agent needs a KUBECONFIG with node-status patch rights — not the server's admin file. Point KUBECONFIG at one before the timer's first fire."
STEP_AGENT_NOTE[storage-sweep]="storage-sweep/install-storage-sweep.sh still pre-gates on this node's tmpfs datastore mount being enabled, which an agent has not, and its unit is ordered against k3s.service rather than k3s-agent.service. It refuses on an agent until that pre-gate and that ordering learn the role — the follow-up on this same plan carrier."

step_label() {  # step_label ID
  if [ "$ROLE" = agent ] && [ -n "${STEP_AGENT_LABEL[$1]:-}" ]; then
    printf '%s' "${STEP_AGENT_LABEL[$1]}"
  else
    printf '%s' "${STEP_LABEL[$1]}"
  fi
}

step_skipped() {  # step_skipped ID -> true when THIS role skips it
  [ "$ROLE" = agent ] && [ -n "${STEP_SKIP[$1]:-}" ]
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
      printf '     reason: %s\n' "${STEP_SKIP[$id]}"
      continue
    fi
    printf 'RUN  [%s] %s\n' "$ROLE" "$(step_label "$id")"
    if [ "$ROLE" = agent ] && [ -n "${STEP_AGENT_NOTE[$id]:-}" ]; then
      printf '     note: %s\n' "${STEP_AGENT_NOTE[$id]}"
    fi
  done
}

run_step() {  # run_step ID
  case "$1" in
    k3s-config)
      "${SCRIPT_DIR}/k3s-config/install-k3s-config.sh" ;;
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
    churn-slot)
      "${SCRIPT_DIR}/node-extended-resource/install-reapply-unit.sh" "${CAPACITY}" ;;
    wedged-runner)
      "${SCRIPT_DIR}/wedged-runner/install-wedged-runner-scan.sh" "${WEDGE_MODE}" ;;
    runner-pod-lifecycle)
      "${SCRIPT_DIR}/runner-pod-lifecycle/install-runner-pod-lifecycle-scan.sh" ;;
    arc-log-archive)
      "${SCRIPT_DIR}/arc-log-archive/install-arc-log-archive.sh" ;;
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
    storage-sweep)
      "${SCRIPT_DIR}/storage-sweep/install-storage-sweep.sh" ;;
    *)
      die "no runner for step '$1' (the step table and run_step have drifted)" ;;
  esac
}

# ---------------------------------------------------------------------------
# --dry-run stops here, having touched nothing at all.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  print_plan
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
  - the heartbeat + Kueue-webhook probe timers: ../../observability/install-observability.sh
  - the warm-cache initial populate (attended): warm-cache/install-warm-cache.sh
  - a k3s restart or reboot: config.yaml changes and the tmpfs cutover take
    effect on the next k3s start; do that at zero active CI jobs, or reboot —
    the reconstruct units then rebuild the cluster from these artifacts.
Verify a boot with the checklist in README.md "Reconstruct-on-boot".
EOF
