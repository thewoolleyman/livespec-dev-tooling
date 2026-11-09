#!/usr/bin/env bash
# apply-kill-matrix.sh — render and apply one rule-26 orchestrator kill-matrix
# Job (./README.md). Run it on a host whose kubectl reaches the cluster.
#
# Usage:
#   apply-kill-matrix.sh ORCHESTRATOR_SHA ENGINE_SHA [WORKERS]
set -euo pipefail

if [[ $# -lt 2 || $# -gt 3 ]]; then
    echo "usage: apply-kill-matrix.sh ORCHESTRATOR_SHA ENGINE_SHA [WORKERS]" >&2
    exit 2
fi

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
manifest="$("${here}/render-kill-matrix-job.sh" --orchestrator-sha "$1" --engine-sha "$2" --workers "${3:-12}")"
printf '%s\n' "${manifest}" | kubectl apply -f -
