#!/usr/bin/env bash
# render-kill-matrix-job.sh — render ./kill-matrix-job-template.yaml into the
# namespace, PVC and Job that run ONE full rule-26 kill matrix of
# livespec-orchestrator-beads-fabro (plan fleet-mutation-testing-rule-26,
# livespec-dev-tooling-fqnbtd). See ./README.md.
#
# Both commits are required and must be full 40-hex SHAs, so a run always names
# exactly the orchestrator tree it measured and the engine that measured it.
# --workers sets the engine's worker count AND the pod's CPU request and limit,
# so the scheduler sees what the run uses.
#
# Writes the manifest to stdout. Applies NOTHING; contacts no cluster.
#
# Usage:
#   render-kill-matrix-job.sh --orchestrator-sha SHA --engine-sha SHA
#                             [--workers N] [--run ID]
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
orchestrator_sha=""
engine_sha=""
workers=12
run="$(date -u +%Y%m%dt%H%M)"

usage() {
    echo "usage: render-kill-matrix-job.sh --orchestrator-sha SHA --engine-sha SHA [--workers N] [--run ID]" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --orchestrator-sha) orchestrator_sha="${2:-}"; shift 2 ;;
        --engine-sha) engine_sha="${2:-}"; shift 2 ;;
        --workers) workers="${2:-}"; shift 2 ;;
        --run) run="${2:-}"; shift 2 ;;
        *) usage ;;
    esac
done

[[ "$orchestrator_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "render-kill-matrix-job: --orchestrator-sha must be a full 40-hex commit" >&2; exit 2; }
[[ "$engine_sha" =~ ^[0-9a-f]{40}$ ]] || { echo "render-kill-matrix-job: --engine-sha must be a full 40-hex commit" >&2; exit 2; }
[[ "$workers" =~ ^[1-9][0-9]*$ ]] || { echo "render-kill-matrix-job: --workers must be a positive integer" >&2; exit 2; }
[[ "$run" =~ ^[a-z0-9-]{1,40}$ ]] || { echo "render-kill-matrix-job: --run must be lowercase letters, digits and dashes" >&2; exit 2; }

sed -e "s/@@ORCH_SHA@@/${orchestrator_sha}/g" \
    -e "s/@@ENGINE_SHA@@/${engine_sha}/g" \
    -e "s/@@WORKERS@@/${workers}/g" \
    -e "s/@@RUN@@/${run}/g" \
    "${here}/kill-matrix-job-template.yaml"
