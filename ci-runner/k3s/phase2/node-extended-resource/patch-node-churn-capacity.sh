#!/usr/bin/env bash
# patch-node-churn-capacity.sh — register ci-runner.io/churn-slot as a
# STATIC Kubernetes extended resource on this k3s node, with capacity
# fixed at the node's safe concurrent-container-churn ceiling.
#
# Why a node-status patch rather than a device plugin: Kubernetes'
# officially documented "extended resource for node" mechanism
# (https://kubernetes.io/docs/tasks/administer-cluster/extended-resource-node/)
# is exactly this — `kubectl patch node ... --subresource=status` — for
# a resource that is a COUNTING ceiling rather than a discoverable
# physical device (there is no /dev/churn-slot to enumerate). A real
# device plugin would be the more robust choice for a multi-node
# cluster; this fleet is single-node today (provision-k3s.sh), so the
# extra machinery is not yet earned — see README.md "Known caveat: the
# node-status patch is not device-plugin-robust" for the exact tradeoff
# and ../VALIDATION_CHECKLIST.md item 3 for confirming it survives a
# real kubelet restart.
#
# CAPACITY VALUE — READ THIS BEFORE RUNNING:
# The capacity is a REQUIRED argument rather than a hardcoded number, and
# the reason is historical but still binding on the shape: during the
# SIDE-BY-SIDE migration window (phases 1-4, livespec-s43svm.14/.15/.16/
# .17) the podman pool was still consuming from the same physical iowait
# budget concurrently, so a flat 482 here (the fleet's podman-era host-wide
# cap, SPECIFICATION/non-functional-requirements.md section "Adaptive JIT
# runner admission budget"; livespec-s43svm.11's measured iowait ceiling)
# while podman also ran near its own 482 would have let the two pools
# jointly imply the very 964 the specification prohibits. The podman pool
# was decommissioned 2026-08-21 and deleted (livespec-s43svm.19); the
# value installed live is 16 (livespec-s43svm.26), and 482 was never
# adopted for this pool — see README.md "Why per-repo quotas summing above
# 482 is safe", ../kueue/DERIVATION.md, and ../VALIDATION_CHECKLIST.md.
set -euo pipefail

USAGE="usage: patch-node-churn-capacity.sh CAPACITY (the host's churn-slot capacity; 16 is the value installed live, and the podman-era 482 was never adopted -- see this script's own header comment and ../kueue/DERIVATION.md)"
CAPACITY="${1:?$USAGE}"
NODE_LABEL_SELECTOR="k3s-role=arc-runner-host"
# NODE_LABEL_SELECTOR matches provision-k3s.sh --node-label.

: "${KUBECONFIG:?set KUBECONFIG to the k3s cluster kubeconfig (see ../provision-k3s.sh)}"

log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
log "1. Resolve the target node(s) by label (single-node today; label-scoped for future growth)"
NODES="$(kubectl get nodes -l "$NODE_LABEL_SELECTOR" -o jsonpath='{.items[*].metadata.name}')"
[ -n "$NODES" ] || { echo "FATAL: no node matches label $NODE_LABEL_SELECTOR" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "2. Patch status.capacity and status.allocatable on each matched node (idempotent)"
for node in $NODES; do
  kubectl patch node "$node" --subresource=status --type=merge -p \
    "{\"status\":{\"capacity\":{\"ci-runner.io/churn-slot\":\"${CAPACITY}\"},\"allocatable\":{\"ci-runner.io/churn-slot\":\"${CAPACITY}\"}}}"
done

# ---------------------------------------------------------------------------
log "3. Verify"
kubectl get nodes -l "$NODE_LABEL_SELECTOR" \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}'

log "DONE. ci-runner.io/churn-slot capacity=${CAPACITY} on every matched node."
