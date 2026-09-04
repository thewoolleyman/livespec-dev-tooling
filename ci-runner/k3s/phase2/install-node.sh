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
# Usage: sudo install-node.sh CAPACITY [WEDGE_MODE]
#   CAPACITY   the ci-runner.io/churn-slot capacity this node carries
#              (64 on poweredge-xubuntu; see kueue/DERIVATION.md — a
#              measurement, deliberately not defaulted)
#   WEDGE_MODE 'report' or 'clear' for the wedged-runner scan (default clear,
#              the live choice on a host with no failure routing)
set -euo pipefail

USAGE="usage: install-node.sh CAPACITY [WEDGE_MODE]   (CAPACITY = churn-slot capacity, e.g. 64; WEDGE_MODE = report|clear, default clear)"
CAPACITY="${1:?$USAGE}"
WEDGE_MODE="${2:-clear}"
[[ "$CAPACITY" =~ ^[0-9]+$ ]] || { echo "FATAL: CAPACITY must be a non-negative integer, got '${CAPACITY}'" >&2; exit 1; }
case "$WEDGE_MODE" in report|clear) ;; *) echo "FATAL: WEDGE_MODE must be report or clear, got '${WEDGE_MODE}'" >&2; exit 1 ;; esac

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

log() { printf '\n#### %s ####\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "FATAL: must run as root" >&2; exit 1; }
[ -f "$KUBECONFIG" ] || { echo "FATAL: ${KUBECONFIG} not found — run ../provision-k3s.sh first" >&2; exit 1; }

log "1/10 k3s server config"
"${SCRIPT_DIR}/k3s-config/install-k3s-config.sh"

log "2/10 inotify instance budget + keyring quota"
"${SCRIPT_DIR}/node-inotify-budget/install-inotify-sysctl.sh"
"${SCRIPT_DIR}/node-keyring-budget/install-keyring-sysctl.sh"

log "2b/10 storage layout (LABEL fstab lines + k3s drop-in; no-op when the tiers are live)"
"${SCRIPT_DIR}/storage-layout/install-storage-layout.sh"

log "2c/10 iDRAC cooling configuration (racadm + fan loop automatic, third-party response off, Minimum Power profile)"
"${SCRIPT_DIR}/host-thermal/install-host-thermal.sh"

log "3/10 AppArmor profile + hook ConfigMap"
"${SCRIPT_DIR}/apparmor/install-apparmor-profile.sh"

log "4/10 churn-slot extended resource (capacity ${CAPACITY}) + reapply timer"
"${SCRIPT_DIR}/node-extended-resource/install-reapply-unit.sh" "${CAPACITY}"

log "5/10 wedged-runner scan (${WEDGE_MODE})"
"${SCRIPT_DIR}/wedged-runner/install-wedged-runner-scan.sh" "${WEDGE_MODE}"

log "5b/10 runner-pod lifecycle scan (report-only; no mode — see its installer's header)"
"${SCRIPT_DIR}/runner-pod-lifecycle/install-runner-pod-lifecycle-scan.sh"

log "6/10 ARC log archive"
"${SCRIPT_DIR}/arc-log-archive/install-arc-log-archive.sh"

log "7/10 boot-time GitHub App secret reinjection unit (enable only)"
"${K3S_DIR}/secret-reinjection/install-secret-reinjection-unit.sh"

log "7b/10 pool-provided sccache binary (node-local; mounted read-only into every job)"
"${SCRIPT_DIR}/sccache/install-sccache-binary.sh"
"${SCRIPT_DIR}/cache-telemetry/install-cache-telemetry.sh"

log "8/10 reconstruct-on-boot converge unit + artifacts (enable only)"
"${SCRIPT_DIR}/reconstruct/install-converge-unit.sh"

log "9/10 tmpfs datastore mount (enable only, never started here)"
"${SCRIPT_DIR}/datastore-tmpfs/install-datastore-tmpfs.sh"

log "10/10 boot-time orphaned-scratch sweep (enable only)"
"${SCRIPT_DIR}/storage-sweep/install-storage-sweep.sh"

log "DONE — node-local mechanisms installed and armed"
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
