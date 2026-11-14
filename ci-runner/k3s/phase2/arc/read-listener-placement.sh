#!/usr/bin/env bash
# read-listener-placement.sh — READ-ONLY read-back of where every ARC runner
# scale set's listener pod runs, against the always-on node label.
#
# WHY IT EXISTS (livespec-dev-tooling-crvvxt). Every scale set's values file
# (./values-*.yaml, ./worker/values-*.yaml) gives its listener pod a
# nodeSelector on `ci-runner.io/always-on=true`, the label a node carries only
# when its committed profile declares ALWAYS_ON_NODE=true. A listener on a node
# that is powered off at will leaves its scale set taking no jobs: on
# 2026-11-12 gamingpc-xubuntu was powered off for a RAM upgrade and the eight
# listener pods on it sat Terminating for about 45 minutes. This script is the
# proof that the rule holds on the live cluster, and the read to make before
# powering a node off.
#
# WHAT IT PRINTS. One line per AutoscalingListener:
#   <scale set>  <listener pod>  <node>  <pod state>  <verdict>
# and then the set of nodes that carry the label.
#
# EXIT STATUS.
#   0  every scale set's listener pod is Running on a node that carries the label
#   1  a listener runs on a node WITHOUT the label, or a scale set has no
#      Running listener pod (none, unscheduled, not Running, or Terminating),
#      or the cluster has no listener at all; each one is named
#   2  a kubectl read failed, or kubectl is not on PATH. A failed read is NEVER
#      read as an empty list: "no listener is misplaced" and "the listeners
#      could not be read" are different answers.
#
# It makes three `kubectl get` calls and no write. kubectl is taken from PATH.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

ALWAYS_ON_LABEL="ci-runner.io/always-on=true"
# Where the ARC controller keeps every AutoscalingListener and its pod — the
# namespace ../reconstruct/converge-ci-stack.sh installs the controller into.
CONTROLLER_NAMESPACE="${ARC_CONTROLLER_NAMESPACE:-arc-systems}"
# Where every AutoscalingRunnerSet (one per scale set) is installed.
RUNNERS_NAMESPACE="${ARC_RUNNERS_NAMESPACE:-arc-runners}"

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 2; }

# Each read ends in `|| exit 2` because bash clears errexit inside `$(...)`: a
# bare assignment from a failed kubectl would leave an empty string that every
# loop below reads as "nothing there".
listeners="$(kubectl -n "$CONTROLLER_NAMESPACE" get autoscalinglisteners.actions.github.com \
  -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.spec.autoscalingRunnerSetName}{"\n"}{end}')" \
  || { echo "FATAL: could not read the AutoscalingListeners in ${CONTROLLER_NAMESPACE}" >&2; exit 2; }
pods="$(kubectl -n "$CONTROLLER_NAMESPACE" get pods \
  -o jsonpath='{range .items[*]}{.metadata.name}{"|"}{.metadata.ownerReferences[0].kind}{"|"}{.metadata.ownerReferences[0].name}{"|"}{.spec.nodeName}{"|"}{.status.phase}{"|"}{.metadata.deletionTimestamp}{"\n"}{end}')" \
  || { echo "FATAL: could not read the pods in ${CONTROLLER_NAMESPACE}" >&2; exit 2; }
# The scale sets themselves, read from where they are installed. A scale set
# with NO AutoscalingListener object at all (the 2026-11-05 shape) appears in
# no listener read, so the listeners alone cannot show it missing.
runner_sets="$(kubectl -n "$RUNNERS_NAMESPACE" get autoscalingrunnersets.actions.github.com \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')" \
  || { echo "FATAL: could not read the AutoscalingRunnerSets in ${RUNNERS_NAMESPACE}" >&2; exit 2; }
labelled="$(kubectl get nodes -l "$ALWAYS_ON_LABEL" -o name)" \
  || { echo "FATAL: could not read the nodes that carry ${ALWAYS_ON_LABEL}" >&2; exit 2; }

declare -A always_on=()
while IFS= read -r line; do
  [ -n "$line" ] || continue
  always_on["${line#node/}"]=1
done <<< "$labelled"

# The listener pod of each AutoscalingListener, by OWNER rather than by name.
# A listener being replaced can briefly own two pods; the one that is not being
# deleted wins, so a healthy replacement is not reported as Terminating.
declare -A pod_of=() node_of=() state_of=()
while IFS='|' read -r pod kind owner node phase deleting; do
  [ -n "$pod" ] || continue
  [ "$kind" = "AutoscalingListener" ] || continue
  if [ -n "${pod_of[$owner]:-}" ] && [ -n "$deleting" ]; then
    continue
  fi
  pod_of["$owner"]="$pod"
  node_of["$owner"]="$node"
  if [ -n "$deleting" ]; then
    state_of["$owner"]="Terminating"
  else
    state_of["$owner"]="${phase:-Unknown}"
  fi
done <<< "$pods"

total=0
bad=0
printf '%-44s %-52s %-32s %-12s %s\n' "SCALE SET" "LISTENER POD" "NODE" "STATE" "VERDICT"
while IFS='|' read -r listener scale_set; do
  [ -n "$listener" ] || continue
  total=$(( total + 1 ))
  pod="${pod_of[$listener]:-}"
  node="${node_of[$listener]:-}"
  state="${state_of[$listener]:-}"
  if [ -z "$pod" ]; then
    verdict="FAIL: no listener pod"
  elif [ -z "$node" ]; then
    verdict="FAIL: listener pod is not scheduled on any node"
  elif [ -z "${always_on[$node]:-}" ]; then
    verdict="FAIL: node does not carry ${ALWAYS_ON_LABEL}"
  elif [ "$state" != "Running" ]; then
    verdict="FAIL: listener pod is ${state}, not Running"
  else
    verdict="ok"
  fi
  [ "$verdict" = "ok" ] || bad=$(( bad + 1 ))
  printf '%-44s %-52s %-32s %-12s %s\n' "${scale_set:-<unnamed>}" "${pod:-<none>}" "${node:-<none>}" "${state:-<none>}" "$verdict"
done <<< "$listeners"

# Every installed scale set must have a listener object. One that has none is
# a scale set that takes no jobs and that the table above cannot show.
declare -A listened=()
while IFS='|' read -r listener scale_set; do
  [ -n "$scale_set" ] || continue
  listened["$scale_set"]=1
done <<< "$listeners"
sets_total=0
while IFS= read -r scale_set; do
  [ -n "$scale_set" ] || continue
  sets_total=$(( sets_total + 1 ))
  [ -z "${listened[$scale_set]:-}" ] || continue
  bad=$(( bad + 1 ))
  printf '%-44s %-52s %-32s %-12s %s\n' "$scale_set" "<none>" "<none>" "<none>" "FAIL: the scale set has no AutoscalingListener"
done <<< "$runner_sets"

printf '\nnodes carrying %s: %s\n' "$ALWAYS_ON_LABEL" "${!always_on[*]}"

if [ "$sets_total" -eq 0 ]; then
  echo "FAIL: ${RUNNERS_NAMESPACE} holds no AutoscalingRunnerSet, so no scale set is installed and there is no placement to confirm"
  exit 1
fi
if [ "$total" -eq 0 ]; then
  echo "FAIL: ${CONTROLLER_NAMESPACE} holds no AutoscalingListener, so no scale set can take a job and there is no placement to confirm"
  exit 1
fi
if [ "$bad" -ne 0 ]; then
  echo "FAIL: ${bad} of ${total} scale set listener(s) are not Running on a node that carries ${ALWAYS_ON_LABEL} (see above)"
  exit 1
fi
echo "OK: all ${total} scale set listener pods are Running on a node that carries ${ALWAYS_ON_LABEL}"
