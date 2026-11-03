#!/usr/bin/env bash
# converge-warm-uv-node-labels.sh — reconcile every pool node's warm-uv
# DaemonSet selector from the installed phase0 profile set, on the server.
#
# The local-path provisioner seeds a PVC only from the `.warm/uv` generation on
# the node that creates it.  The server's local mount check in
# converge-ci-stack.sh therefore cannot cover an already-registered agent: each
# `CI_NODE_FACILITIES=full` profile needs this label, while `none` must remove
# it.  The ci_converge_unit role installs every pool profile beside this script
# so the server can make that decision without a checkout or an agent restart.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LABEL_KEY="ci-runner.io/warm-uv-cache"
LABEL_VALUE="true"
LABEL="${LABEL_KEY}=${LABEL_VALUE}"
WAIT_SECONDS="${CI_WARM_UV_LABEL_WAIT_SECONDS:-120}"
POLL_SECONDS="${CI_WARM_UV_LABEL_POLL_SECONDS:-2}"

if [ -n "${CI_WARM_UV_LABEL_PROFILES_DIR:-}" ]; then
  PROFILES_DIR="${CI_WARM_UV_LABEL_PROFILES_DIR}"
elif [ -d "${SCRIPT_DIR}/profiles" ]; then
  PROFILES_DIR="${SCRIPT_DIR}/profiles"
elif [ -d "${SCRIPT_DIR}/../../phase0-bare-metal/profiles" ]; then
  PROFILES_DIR="$(cd "${SCRIPT_DIR}/../../phase0-bare-metal/profiles" && pwd)"
else
  echo "FATAL: no pool profiles directory is available for warm-uv labels" >&2
  exit 1
fi

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 1; }

profile_value() { # profile_value FILE KEY
  sed -n "s/^$2=//p" "$1" | head -n1 | tr -d '[:space:]'
}

node_registered() { # node_registered NODE
  local answer
  if answer="$(kubectl get node "$1" -o name 2>&1)"; then
    return 0
  fi
  case "$answer" in
    *"(NotFound)"*) ;;
    *) printf '  kubectl: %s\n' "$answer" >&2 ;;
  esac
  return 1
}

wait_for_registration() { # wait_for_registration NODE
  local node="$1" attempts attempt=0
  attempts=$(( WAIT_SECONDS / POLL_SECONDS ))
  [ "$attempts" -ge 1 ] || attempts=1
  while [ "$attempt" -lt "$attempts" ]; do
    if node_registered "$node"; then
      [ "$attempt" -eq 0 ] || printf '  %s registered after %ss\n' "$node" "$(( attempt * POLL_SECONDS ))"
      return 0
    fi
    attempt=$(( attempt + 1 ))
    printf '  waiting for %s to register (%s/%s)...\n' "$node" "$attempt" "$attempts"
    sleep "$POLL_SECONDS"
  done
  return 1
}

full_nodes=()
other_nodes=()
unreadable=0
for profile in "${PROFILES_DIR}"/*.env; do
  [ -f "$profile" ] || continue
  node="$(profile_value "$profile" NODE_NAME)"
  facilities="$(profile_value "$profile" CI_NODE_FACILITIES)"
  [ -n "$facilities" ] || facilities=full
  if [ -z "$node" ]; then
    echo "WARN: ${profile} has no NODE_NAME; skipping its warm-uv label" >&2
    unreadable=1
    continue
  fi
  case "$facilities" in
    full) full_nodes+=("$node") ;;
    none|runner-only) other_nodes+=("$node") ;;
    *)
      echo "WARN: ${profile} has CI_NODE_FACILITIES=${facilities}; refusing to change ${node}" >&2
      unreadable=1
      ;;
  esac
done

unreconciled=0
for node in ${full_nodes[@]+"${full_nodes[@]}"}; do
  if wait_for_registration "$node" \
    && kubectl label --overwrite node "$node" "$LABEL" >/dev/null; then
    printf '%s: %s asserted\n' "$node" "$LABEL"
  else
    echo "WARN: could not assert ${LABEL} on ${node}; its local-path volumes remain cold" >&2
    unreconciled=1
  fi
done

# Ask the selector's own question, then remove its label only from nodes the
# installed profiles explicitly close to CI work.  An absent Node has no label
# to remove and will be reconciled after it registers on a later converge.
labelled="$(kubectl get nodes -l "$LABEL" -o name 2>/dev/null || true)"
for node in ${other_nodes[@]+"${other_nodes[@]}"}; do
  case $'\n'"${labelled}"$'\n' in
    *$'\n'"node/${node}"$'\n'*) ;;
    *) continue ;;
  esac
  if kubectl label node "$node" "${LABEL_KEY}-" >/dev/null; then
    printf '%s: %s removed (CI_NODE_FACILITIES=none)\n' "$node" "$LABEL_KEY"
  else
    echo "WARN: could not remove ${LABEL_KEY} from ${node}" >&2
    unreconciled=1
  fi
done

kubectl get nodes -L "$LABEL_KEY" || true
if [ "$unreadable" -ne 0 ] || [ "$unreconciled" -ne 0 ]; then
  exit 1
fi
