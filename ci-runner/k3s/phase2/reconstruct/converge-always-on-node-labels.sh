#!/usr/bin/env bash
# converge-always-on-node-labels.sh — reconcile EVERY ci_pool node's ALWAYS-ON
# label to its committed phase0 profile's ALWAYS_ON_NODE, on the control plane,
# at BOOT.
#
# WHY IT EXISTS (livespec-dev-tooling-crvvxt). Every ARC runner scale set's
# listener pod carries a nodeSelector on `ci-runner.io/always-on=true`
# (../arc/values-*.yaml `listenerTemplate`), so a listener is only ever placed
# on a node nobody powers off at will. On 2026-11-12 gamingpc-xubuntu was
# powered off for a RAM upgrade and the eight listener pods on it sat
# Terminating for about 45 minutes; a scale set with no listener takes no jobs.
#
# k3s applies `--node-label` at node REGISTRATION only and this host's datastore
# is a tmpfs, so after a control-plane reboot every Node object is re-created
# carrying only what its own kubelet was started with. Without this reconcile
# no node would carry the label after a reboot, and EVERY listener would stay
# Pending. ./converge-factory-node-labels.sh's header records the same defect
# for the factory label, measured 2026-10-16, and why the reconcile lives on the
# control plane and not in each node's start configuration (nothing here may
# restart a k3s-agent). This script is that reconcile for the second
# profile-declared label, and ../../../../ansible/roles/node_labels is its
# apply-time twin.
#
# UNLIKE THE FACTORY LABEL, THIS ONE GATES CI. ./converge-ci-stack.sh therefore
# runs it TWICE: once before the ARC controller with no registration wait
# (CI_ALWAYS_ON_LABEL_WAIT_SECONDS=0), which labels the server itself and every
# agent already registered so the listeners can schedule the moment they are
# created, and once at the end with the bounded wait, for agents that
# re-registered behind the control plane.
#
# THE REMOVAL HALF keeps a profile edit takeable: ../../provision-k3s.sh writes
# the label into an always-on node's install command, so a node retired by a
# profile edit registers with it again. It removes the label from EVERY
# labelled node that no profile declares always-on, a node with no profile
# included; only a node whose profile could not be read is left as it is. Removing the label does NOT move a
# listener already running there (a nodeSelector is checked at scheduling
# only); ../arc/read-listener-placement.sh reads that back.
#
# The profiles are read from ./profiles/ beside this script on the host (the
# ci_converge_unit Ansible role installs every ci_pool node's committed profile
# there) or from ../../phase0-bare-metal/profiles in a checkout.
#
# EXITS NON-ZERO when it could not reconcile every node; the caller WARNs.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The label, as the two spellings kubectl needs: `key=value` to set and a bare
# `key-` to remove.
ALWAYS_ON_LABEL_KEY="ci-runner.io/always-on"
ALWAYS_ON_LABEL_VALUE="true"
ALWAYS_ON_LABEL="${ALWAYS_ON_LABEL_KEY}=${ALWAYS_ON_LABEL_VALUE}"

# The bounded wait for a node that has not re-registered yet. 0 means one probe
# and no wait, which is what the early pass asks for.
WAIT_SECONDS="${CI_ALWAYS_ON_LABEL_WAIT_SECONDS:-120}"
POLL_SECONDS="${CI_ALWAYS_ON_LABEL_POLL_SECONDS:-2}"

if [ -n "${CI_ALWAYS_ON_LABEL_PROFILES_DIR:-}" ]; then
  PROFILES_DIR="${CI_ALWAYS_ON_LABEL_PROFILES_DIR}"
elif [ -d "${SCRIPT_DIR}/profiles" ]; then
  PROFILES_DIR="${SCRIPT_DIR}/profiles"
elif [ -d "${SCRIPT_DIR}/../../phase0-bare-metal/profiles" ]; then
  PROFILES_DIR="$(cd "${SCRIPT_DIR}/../../phase0-bare-metal/profiles" && pwd)"
else
  echo "FATAL: no committed profiles directory beside ${SCRIPT_DIR} and none at ../../phase0-bare-metal/profiles — this converge decides no node's posture of its own, so it cannot run without them. Re-install the boot tree with the ci_converge_unit Ansible role (just ansible-apply ansible/ci-pool.yml)" >&2
  exit 1
fi

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 1; }

log() { printf '\n== %s ==\n' "$*"; }

# One scalar out of a profile: the FIRST occurrence, whitespace stripped — the
# same convention ./converge-factory-node-labels.sh and the Ansible roles use.
profile_value() {  # profile_value FILE KEY
  sed -n "s/^$2=//p" "$1" | sed -n 1p | tr -d '[:space:]'
}

# Is this node registered in the API yet? kubectl's exact `(NotFound)` is
# something to wait for; any OTHER failure is reported as itself.
node_registered() {  # node_registered NODE
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

wait_for_registration() {  # wait_for_registration NODE
  local node="$1" attempts attempt=0
  attempts=$(( WAIT_SECONDS / POLL_SECONDS ))
  [ "$attempts" -ge 1 ] || attempts=1
  while :; do
    if node_registered "$node"; then
      [ "$attempt" -eq 0 ] || printf '  %s registered after %ss\n' "$node" "$(( attempt * POLL_SECONDS ))"
      return 0
    fi
    attempt=$(( attempt + 1 ))
    [ "$attempt" -lt "$attempts" ] || return 1
    printf '  waiting for %s to re-register (%s/%s)...\n' "$node" "$attempt" "$attempts"
    sleep "$POLL_SECONDS"
  done
}

declared_always_on=()
declared_plain=()
# Nodes whose profile names them but whose ALWAYS_ON_NODE could not be read,
# and the count of profiles that name no node. Step 3 removes no label on
# either account.
skipped_unreadable=()
nameless_profiles=0
unreadable=0
unreconciled=0

# ---------------------------------------------------------------------------
log "always-on-node-labels 1. Read every committed profile's ALWAYS_ON_NODE"
printf 'profiles: %s\n' "$PROFILES_DIR"
for profile in "${PROFILES_DIR}"/*.env; do
  [ -f "$profile" ] || continue
  node="$(profile_value "$profile" NODE_NAME)"
  if [ -z "$node" ]; then
    echo "WARN: ${profile} declares no NODE_NAME — skipping it. The label is reconciled by NODE name and this converge must not guess one from a filename"
    unreadable=1
    nameless_profiles=$(( nameless_profiles + 1 ))
    continue
  fi
  always_on="$(profile_value "$profile" ALWAYS_ON_NODE)"
  # A missing key is the phase0 parser's own default, `false`: a node whose
  # profile says nothing is never chosen for a listener.
  [ -n "$always_on" ] || always_on=false
  case "$always_on" in
    true) declared_always_on+=("$node") ;;
    false) declared_plain+=("$node") ;;
    *)
      # A typo must not read as "not true" and silently REMOVE a live label.
      echo "WARN: ${profile} declares ALWAYS_ON_NODE='${always_on}', which is neither 'true' nor 'false' — skipping ${node} rather than reading the typo as 'not true' and removing a live always-on label"
      skipped_unreadable+=("$node")
      unreadable=1
      ;;
  esac
done
printf 'declared always-on nodes: %s\n' "${declared_always_on[*]:-<none>}"
printf 'declared not-always-on nodes: %s\n' "${declared_plain[*]:-<none>}"
if [ "${#declared_always_on[@]}" -eq 0 ]; then
  echo "WARN: no committed profile declares ALWAYS_ON_NODE=true, so no node can host an ARC listener pod and every runner scale set would take no jobs"
  unreconciled=1
fi

# ---------------------------------------------------------------------------
log "always-on-node-labels 2. Assert the label on every DECLARED always-on node"
for node in ${declared_always_on[@]+"${declared_always_on[@]}"}; do
  if ! wait_for_registration "$node"; then
    echo "WARN: ${node} is not registered (waited ${WAIT_SECONDS}s) — ${ALWAYS_ON_LABEL} is NOT asserted on it this pass, so no listener pod can be placed on it. Re-run this converge (systemctl start converge-ci-stack.service) or apply the label's role (just ansible-apply ansible/ci-pool.yml -l ${node} --tags node_labels)"
    unreconciled=1
    continue
  fi
  if kubectl label --overwrite node "$node" "$ALWAYS_ON_LABEL" >/dev/null; then
    printf '  %s: %s asserted\n' "$node" "$ALWAYS_ON_LABEL"
  else
    echo "WARN: could not label ${node} with ${ALWAYS_ON_LABEL} — no listener pod can be placed on it until it is set (kubectl label --overwrite node ${node} ${ALWAYS_ON_LABEL})"
    unreconciled=1
  fi
done

# ---------------------------------------------------------------------------
log "always-on-node-labels 3. Remove the label from every labelled node that no profile declares always-on"
# EVERY OTHER NODE MUST NOT CARRY IT, so the walk is over the nodes that carry
# the label, not over the profiles that say `false`: a labelled node with NO
# committed profile (a homelab container worker, or a node labelled by hand)
# is unlabelled too. Two kinds of node are left as they are and reported,
# because an unreadable profile is not a declaration of `false`:
#   - a node whose profile was skipped at step 1 for a value that is neither
#     `true` nor `false`;
#   - while a profile at step 1 declared no NODE_NAME, any labelled node that
#     no readable profile names: it may be that profile's node.
#
# A FAILED READ IS NOT AN EMPTY LIST: reading "kubectl failed" as "no node
# carries the label" would skip every removal and report success.
if labelled="$(kubectl get nodes -l "$ALWAYS_ON_LABEL" -o name)"; then
  while IFS= read -r labelled_node; do
    [ -n "$labelled_node" ] || continue
    node="${labelled_node#node/}"
    case " ${declared_always_on[*]:-} " in
      *" ${node} "*) continue ;;
    esac
    case " ${skipped_unreadable[*]:-} " in
      *" ${node} "*)
        printf '  %s: %s left as it is (its profile could not be read; see step 1)\n' "$node" "$ALWAYS_ON_LABEL_KEY"
        continue
        ;;
    esac
    case " ${declared_plain[*]:-} " in
      *" ${node} "*) why="its profile does not declare ALWAYS_ON_NODE=true" ;;
      *)
        if [ "$nameless_profiles" -ne 0 ]; then
          echo "WARN: ${node} carries ${ALWAYS_ON_LABEL_KEY} and no readable profile names it, but ${nameless_profiles} profile(s) declare no NODE_NAME (see step 1) and one may be this node's — leaving its label as it is rather than removing it on a guess"
          unreconciled=1
          continue
        fi
        why="it has no committed profile"
        ;;
    esac
    # The trailing `-` is kubectl's remove syntax.
    if kubectl label node "$node" "${ALWAYS_ON_LABEL_KEY}-" >/dev/null; then
      printf '  %s: %s removed (%s)\n' "$node" "$ALWAYS_ON_LABEL_KEY" "$why"
    else
      echo "WARN: could not remove ${ALWAYS_ON_LABEL_KEY} from ${node} (${why}) — a listener pod can still be placed on a node that is powered off at will"
      unreconciled=1
    fi
  done <<< "$labelled"
else
  echo "WARN: could not read which nodes carry ${ALWAYS_ON_LABEL}, so no stale label was removed this pass"
  unreconciled=1
fi

# ---------------------------------------------------------------------------
log "always-on-node-labels 4. Verify (the column an operator reads after a reboot)"
kubectl get nodes -L "$ALWAYS_ON_LABEL_KEY" || true

if [ "$unreconciled" -ne 0 ] || [ "$unreadable" -ne 0 ]; then
  echo "WARN: the ${ALWAYS_ON_LABEL_KEY} label is NOT reconciled on every ci_pool node (see above)"
  exit 1
fi
echo "DONE. ${ALWAYS_ON_LABEL_KEY} reconciled from the committed profiles on every ci_pool node."
