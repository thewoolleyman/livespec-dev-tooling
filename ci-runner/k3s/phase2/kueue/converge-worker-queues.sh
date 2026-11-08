#!/usr/bin/env bash
# converge-worker-queues.sh — render and apply the container-worker Kueue
# queues (./worker/cluster-queue-*.yaml) with a quota equal to the sum of the
# enrolled workers' derived ci-runner.io/churn-slot capacity
# (livespec-dev-tooling-ko26ez.7). converge-ci-stack.sh runs it after the
# committed queues; homelab-worker/enroll-workload-classes.sh runs it after
# enrolling or un-enrolling a worker, so the cohort quota is reconciled in the
# same operation. Each template names its architecture in its file name
# (…-<arch>.yaml) and sums only workers of that architecture.
#
# Requires kubectl with KUBECONFIG pointed at the cluster. --dry-run prints the
# rendered manifests and applies nothing.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dir="${WORKER_QUEUE_DIR:-$here/worker}"
dry_run=0
[ "${1:-}" = --dry-run ] && dry_run=1

for template in "$dir"/cluster-queue-*.yaml; do
  [ -e "$template" ] || exit 0
  base="${template##*/}"
  arch="${base%.yaml}"
  arch="${arch##*-}"
  slots="$(kubectl get nodes -l "homelab-worker.livespec.dev/class=worker,kubernetes.io/arch=$arch" \
    -o jsonpath='{range .items[*]}{.status.capacity.ci-runner\.io/churn-slot}{"\n"}{end}' |
    awk '/^[0-9]+$/ { s += $1 } END { print s + 0 }')"
  rendered="$(sed "s|@WORKER_CHURN_SLOTS@|$slots|" "$template")"
  echo "converge-worker-queues: $base -> $slots churn slots from enrolled $arch workers"
  if [ "$dry_run" -eq 1 ]; then
    printf '%s\n' "$rendered"
  else
    printf '%s\n' "$rendered" | kubectl apply -f - >/dev/null
  fi
done
