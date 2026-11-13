#!/usr/bin/env bash
# Render only: no cluster access, deployment or mutation execution.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
target_sha=""
engine_sha=""
workers=""
run=""
node=""
memory=""
storage=""

refuse() {
    echo "render-runtime-job: $1" >&2
    exit 2
}

while [[ $# -gt 0 ]]; do
    [[ $# -ge 2 ]] || refuse "each flag needs a value"
    case "$1" in
        --target-sha) target_sha="$2" ;;
        --engine-sha) engine_sha="$2" ;;
        --workers) workers="$2" ;;
        --run) run="$2" ;;
        --node) node="$2" ;;
        --memory) memory="$2" ;;
        --storage) storage="$2" ;;
        *) refuse "unknown flag: $1" ;;
    esac
    shift 2
done

[[ "$target_sha" =~ ^[0-9a-f]{40}$ ]] || refuse "--target-sha must be a full 40-hex commit"
[[ "$engine_sha" =~ ^[0-9a-f]{40}$ ]] || refuse "--engine-sha must be a full 40-hex commit"
[[ "$workers" =~ ^[1-9][0-9]*$ ]] || refuse "--workers must be an explicit positive integer"
[[ ${#run} -le 40 && "$run" =~ ^[a-z0-9]([a-z0-9-]*[a-z0-9])?$ ]] || refuse "--run must be 1-40 lowercase letters, digits or internal dashes"
[[ ${#node} -le 63 && "$node" =~ ^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$ ]] || refuse "--node must name the inventory node"
[[ "$memory" =~ ^[1-9][0-9]*(Mi|Gi)$ ]] || refuse "--memory must be an explicit Mi or Gi quantity"
[[ "$storage" =~ ^[1-9][0-9]*(Mi|Gi)$ ]] || refuse "--storage must be an explicit Mi or Gi quantity"

sed -e "s/@@TARGET_SHA@@/${target_sha}/g" \
    -e "s/@@ENGINE_SHA@@/${engine_sha}/g" \
    -e "s/@@WORKERS@@/${workers}/g" \
    -e "s/@@RUN@@/${run}/g" \
    -e "s/@@NODE@@/${node}/g" \
    -e "s/@@MEMORY@@/${memory}/g" \
    -e "s/@@STORAGE@@/${storage}/g" \
    "${here}/runtime-job-template.yaml"
