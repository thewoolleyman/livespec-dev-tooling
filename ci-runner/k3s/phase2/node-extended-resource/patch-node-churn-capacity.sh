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
# The steady-state target (once the podman pool is fully retired,
# livespec-s43svm.19) is 482 — the fleet's existing physical host-wide
# cap (SPECIFICATION/non-functional-requirements.md section "Adaptive
# JIT runner admission budget"; livespec-s43svm.11's measured iowait
# ceiling). During the SIDE-BY-SIDE migration window (phases 1-4,
# livespec-s43svm.14/.15/.16/.17), the podman pool is STILL consuming
# from that same physical iowait budget concurrently, so setting this
# k3s pool's capacity to a flat 482 while podman also runs near its own
# 482 would let the two pools jointly imply the very 964 the
# specification prohibits. This script therefore takes the capacity as
# a REQUIRED argument rather than hardcoding either number — see
# README.md "Why per-repo quotas summing above 482 is safe" and
# ../VALIDATION_CHECKLIST.md item 4 for the joint-budget coordination
# this implies across the two pools during cutover.
set -euo pipefail

USAGE="usage: patch-node-churn-capacity.sh CAPACITY (e.g. a small phase-2 provisional value while zero real traffic is routed here, or 482 only once the podman pool is fully retired -- livespec-s43svm.19; see this script's own header comment)"
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
