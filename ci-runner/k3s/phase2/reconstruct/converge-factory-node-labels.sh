#!/usr/bin/env bash
# converge-factory-node-labels.sh — reconcile EVERY ci_pool node's FACTORY label
# to its committed phase0 profile's FACTORY_NODE, on the control plane, at BOOT.
#
# WHY IT EXISTS. k3s applies `--node-label` at node REGISTRATION only, and this
# host's k3s datastore is a tmpfs (../datastore-tmpfs/): every Node object is
# RE-CREATED when its node re-registers after a control-plane reboot, carrying
# only the labels that node's own kubelet was started with. ../../provision-k3s.sh
# puts the factory label into the k3s install command, so a node whose agent has
# started since that install carries it — and a node whose label was set
# AFTERWARDS, by ../../../../ansible/roles/node_labels, does not, because that
# role reconciles only on a `ci-pool.yml` apply.
#
# Measured live 2026-10-16 (item livespec-dev-tooling-izlx4g): poweredge-xubuntu
# rebooted at ~16:55Z, the boot converge reported Result=success at 16:57Z, and
# once all three nodes were Ready `kubectl get nodes -L ci-runner.io/factory`
# showed the label on hp-xubuntu ALONE. gmktec-xubuntu and poweredge-xubuntu had
# re-registered without it, so the kubernetes-sandbox-backend plugin's
# `ci-runner.io/factory=true` selector matched one node of three until an
# operator ran an apply. Nothing errored: a selector that matches fewer nodes
# than it should simply schedules less, which is why this went unnoticed until
# somebody read the column.
#
# WHY HERE AND NOT IN EACH NODE'S START CONFIGURATION. Rendering the label into
# /etc/rancher/k3s/config.yaml.d — what ../k3s-config/ does for the node TAINT —
# makes it a property of the next REGISTRATION, which is the durable shape. But
# it only reaches a node once that node's k3s-agent has RESTARTED, and nothing
# in this tree may restart an agent: it kills every CI job running on it
# (item livespec-dev-tooling-mbj3kz, and ../../../../ansible/roles/k3s_config's
# own refusal to carry a `state:`). So between the apply that rendered the file
# and the next agent restart, a control-plane reboot would still lose the label
# on exactly the nodes that lost it on 2026-10-16. A reconcile on the control
# plane needs no restart anywhere and heals the nodes that are ALREADY RUNNING,
# which after a control-plane-only reboot is every node in the pool.
#
# SCOPE — the FACTORY label ONLY. This is the same reconcile
# ../../../../ansible/roles/node_labels performs, moved onto the boot path, and
# it keeps that role's scope exactly: it never reads, adds or removes any other
# label. `k3s-role=arc-runner-host` is the RUNNER role and belongs to the install
# command; `ci-runner.io/cache-tier-carrier` is asserted by
# ./converge-ci-stack.sh's own step 1c against a live mount.
#
# THE REMOVAL HALF IS NOT OPTIONAL. ../../provision-k3s.sh writes
# `--node-label ci-runner.io/factory=true` into a factory node's install command,
# so a node retired from the pool by a profile edit carries the label AGAIN at
# its next registration. A converge that only ever ADDED would make that edit
# un-takeable: an operator would remove the label, the next reboot would put it
# back, and the selector would keep scheduling onto a node nobody declared.
#
# THE PROFILES ARE READ FROM THE HOST, because the host has no checkout. The
# ci_converge_unit Ansible role installs every ci_pool node's committed profile
# into ./profiles/ beside this script at APPLY time — when an operator is
# present and a failure is loud — and /usr/local/lib/ci-runner-k3s/ is ordinary
# disk that survives the reboot the tmpfs datastore does not. The committed
# profile stays the single source of every node's posture.
#
# EXITS NON-ZERO when it could not reconcile every node, and ./converge-ci-stack.sh
# turns that into a WARN and carries on: a missing factory label costs factory
# dispatch, not CI, so it must never take Kueue, ARC and the scale sets down with
# it. The step still has to SAY so, because the entire cost of the 2026-10-16
# defect was that nothing said anything.
#
# Requires: kubectl with KUBECONFIG pointed at the k3s cluster.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# The label, as the two spellings kubectl needs: `key=value` to set and a bare
# `key-` to remove. Composed once here for the same reason
# ../../../../ansible/roles/node_labels/defaults/main.yml composes it once —
# two spellings of one fact is two facts.
FACTORY_LABEL_KEY="ci-runner.io/factory"
FACTORY_LABEL_VALUE="true"
FACTORY_LABEL="${FACTORY_LABEL_KEY}=${FACTORY_LABEL_VALUE}"

# The bounded wait for a node that has not re-registered yet. The same bound and
# cadence ./converge-ci-stack.sh step 1 waits for its own node with, and for the
# same reason: a (re)registration on this hardware completes in single-digit
# seconds, and a wait that is not bounded is a boot unit that never exits.
WAIT_SECONDS="${CI_FACTORY_LABEL_WAIT_SECONDS:-120}"
POLL_SECONDS="${CI_FACTORY_LABEL_POLL_SECONDS:-2}"

# Where the committed profiles are, resolved so ONE script works from the
# installed tree and from a checkout, exactly as ./converge-ci-stack.sh resolves
# its artifact directories.
#   - CI_FACTORY_LABEL_PROFILES_DIR wins if set.
#   - INSTALLED layout: the ci_converge_unit role copies the pool's profiles into
#     ./profiles/ beside this script in /usr/local/lib/ci-runner-k3s/. A
#     SUBDIRECTORY and not that flat directory on purpose: node_extended_resource
#     already installs THIS node's own profile there as `<node>.env`, and one
#     file may have one owner.
#   - REPO layout: this file is phase2/reconstruct/, so the profiles are at
#     ../../phase0-bare-metal/profiles.
if [ -n "${CI_FACTORY_LABEL_PROFILES_DIR:-}" ]; then
  PROFILES_DIR="${CI_FACTORY_LABEL_PROFILES_DIR}"
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

# One scalar out of a profile: the FIRST occurrence, whitespace stripped. The
# `| first` of the `regex_findall('^KEY=(.*)$') | first` expression
# ../../../../ansible/roles/node_labels, node_taints and k3s_config all use on
# this same directory of profiles — NOT the `tail -n1` of ./converge-ci-stack.sh
# step 1b's own helper. The two conventions differ only on a profile that
# declared a key twice, and the role that reconciles THIS label is the one this
# script must never disagree with.
profile_value() {  # profile_value FILE KEY
  sed -n "s/^$2=//p" "$1" | head -n1 | tr -d '[:space:]'
}

# Is this node registered in the API yet? A node still re-registering answers
# kubectl's exact `Error from server (NotFound): nodes "<name>" not found`; that
# is something to wait for, and any OTHER non-zero is reported as itself rather
# than swallowed. The literal `(NotFound)` reason token is matched rather than
# the bare words "NotFound"/"not found", so an unrelated future stderr that
# merely contains them is not read as an absent node — the same discrimination
# ../../../../ansible/roles/node_labels makes.
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

# The bounded wait itself. Polls rather than `kubectl wait`, because the object
# does not exist yet and `wait` on an absent name is an error, not a wait.
wait_for_registration() {  # wait_for_registration NODE
  local node="$1" attempts attempt=0
  attempts=$(( WAIT_SECONDS / POLL_SECONDS ))
  [ "$attempts" -ge 1 ] || attempts=1
  while [ "$attempt" -lt "$attempts" ]; do
    if node_registered "$node"; then
      [ "$attempt" -eq 0 ] || printf '  %s registered after %ss\n' "$node" "$(( attempt * POLL_SECONDS ))"
      return 0
    fi
    attempt=$(( attempt + 1 ))
    printf '  waiting for %s to re-register (%s/%s)...\n' "$node" "$attempt" "$attempts"
    sleep "$POLL_SECONDS"
  done
  return 1
}

declared_factory=()
declared_plain=()
unreadable=0
unreconciled=0

# ---------------------------------------------------------------------------
log "factory-node-labels 1. Read every committed profile's FACTORY_NODE"
printf 'profiles: %s\n' "$PROFILES_DIR"
for profile in "${PROFILES_DIR}"/*.env; do
  [ -f "$profile" ] || continue
  node="$(profile_value "$profile" NODE_NAME)"
  if [ -z "$node" ]; then
    echo "WARN: ${profile} declares no NODE_NAME — skipping it. The label is reconciled by NODE name and this converge must not guess one from a filename"
    unreadable=1
    continue
  fi
  factory="$(profile_value "$profile" FACTORY_NODE)"
  # A missing key is the phase0 parser's own default, `false`
  # (../../phase0-bare-metal/profile.sh) — the posture of every profile written
  # before the key existed — so a profile that predates it is a no-op here
  # rather than an error.
  [ -n "$factory" ] || factory=false
  case "$factory" in
    true) declared_factory+=("$node") ;;
    false) declared_plain+=("$node") ;;
    *)
      # Re-asserted rather than assumed: this script reads the one line it needs
      # instead of going through the phase0 parser, and without the enum a typo
      # reads as "not true" and SILENTLY REMOVES a live factory label — a worse
      # outcome than the defect this converge repairs, because the selector
      # would lose a node that was working.
      echo "WARN: ${profile} declares FACTORY_NODE='${factory}', which is neither 'true' nor 'false' — skipping ${node} rather than reading the typo as 'not true' and removing a live factory label"
      unreadable=1
      ;;
  esac
done
printf 'declared factory nodes: %s\n' "${declared_factory[*]:-<none>}"
printf 'declared non-factory nodes: %s\n' "${declared_plain[*]:-<none>}"

# ---------------------------------------------------------------------------
log "factory-node-labels 2. Assert the label on every DECLARED factory node"
# THE HALF THAT REPAIRS THE DEFECT, and the wait is the load-bearing part of it.
# This converge runs on the server the moment k3s is up; an agent re-registers
# against the re-created datastore some seconds behind it. A reconcile that read
# "not registered" as "nothing to do" would miss exactly the nodes that lose the
# label — the agents — and report success doing it.
#
# `kubectl label --overwrite` IS the idempotent form: a bare `kubectl label`
# fails once the key exists, and a node that already carries the label is the
# ordinary case on a re-run.
for node in ${declared_factory[@]+"${declared_factory[@]}"}; do
  if ! wait_for_registration "$node"; then
    echo "WARN: ${node} did not register within ${WAIT_SECONDS}s — ${FACTORY_LABEL} is NOT asserted on it this boot, so the sandbox backend's selector cannot see it. Re-run this converge (systemctl start converge-ci-stack.service) or apply the label's role (just ansible-apply ansible/ci-pool.yml -l ${node} --tags node_labels)"
    unreconciled=1
    continue
  fi
  if kubectl label --overwrite node "$node" "$FACTORY_LABEL" >/dev/null; then
    printf '  %s: %s asserted\n' "$node" "$FACTORY_LABEL"
  else
    echo "WARN: could not label ${node} with ${FACTORY_LABEL} — the sandbox backend's selector cannot see it until it is set (kubectl label --overwrite node ${node} ${FACTORY_LABEL})"
    unreconciled=1
  fi
done

# ---------------------------------------------------------------------------
log "factory-node-labels 3. Remove the label from every node whose profile no longer declares it"
# ASKED AS A LABEL SELECTOR, which is the question the label exists to answer:
# the kubernetes-sandbox-backend selects factory capacity with exactly this
# selector, so a node that does not appear here is a node that plugin cannot
# see. It also needs no inner escaping of a key carrying a dot and a slash,
# which a `-o jsonpath` read of the same label would.
#
# A node that is not registered is not in the answer and needs no wait: it has
# no label to remove, and it will register with whatever its own install command
# names — which is what step 2 above, or the next boot, reconciles.
labelled="$(kubectl get nodes -l "$FACTORY_LABEL" -o name 2>/dev/null || true)"
for node in ${declared_plain[@]+"${declared_plain[@]}"}; do
  case $'\n'"${labelled}"$'\n' in
    *$'\n'"node/${node}"$'\n'*) ;;
    *) continue ;;
  esac
  # The trailing `-` is kubectl's remove syntax.
  if kubectl label node "$node" "${FACTORY_LABEL_KEY}-" >/dev/null; then
    printf '  %s: %s removed (its profile declares FACTORY_NODE=false)\n' "$node" "$FACTORY_LABEL_KEY"
  else
    echo "WARN: could not remove ${FACTORY_LABEL_KEY} from ${node}, whose profile no longer declares it — the selector keeps scheduling factory work onto it"
    unreconciled=1
  fi
done

# ---------------------------------------------------------------------------
log "factory-node-labels 4. Verify (the column an operator reads after a reboot)"
kubectl get nodes -L "$FACTORY_LABEL_KEY" || true

if [ "$unreconciled" -ne 0 ] || [ "$unreadable" -ne 0 ]; then
  echo "WARN: the ${FACTORY_LABEL_KEY} label is NOT reconciled on every ci_pool node (see above)"
  exit 1
fi
echo "DONE. ${FACTORY_LABEL_KEY} reconciled from the committed profiles on every ci_pool node."
