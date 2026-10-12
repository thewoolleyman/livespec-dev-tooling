#!/usr/bin/env bash
# patch-node-churn-capacity.sh — register ci-runner.io/churn-slot as a
# STATIC Kubernetes extended resource on THIS ONE node, with capacity fixed at
# the node's safe concurrent-container-churn ceiling, read from the node's own
# phase0-bare-metal PROFILE.
#
# PER-NODE, BY NAME — the R5 change (livespec plan k3s-on-gmktec-for-vps-usage,
# epic livespec-sab5gn, resolving livespec-dev-tooling-xa6o). This script used to
# resolve its targets with `kubectl get nodes -l k3s-role=arc-runner-host` (a
# LIST) and patch EVERY matched node with ONE uniform capacity. That was correct
# only while the pool was one node: churn-slot capacity is PER-NODE (each node
# advertises its own status.capacity) while the Kueue cohort quota is
# cluster-wide, so a second node with a DIFFERENT real ceiling cannot share one
# number. It now patches the SINGLE node the profile NAMES with the capacity the
# profile DECLARES. Two consequences:
#   * the SERVER's reapply timer patches ONLY its own node, so it no longer
#     stamps the agent with the server's number;
#   * a node-local AGENT timer can use the scoped get/patch-on-nodes/status
#     credential ../node-status-credential/ mints, because that credential is
#     restricted by resourceNames to ONE named node and a LIST verb is not
#     restrictable by resourceNames at all (see that directory's README). A
#     by-name patch is the only shape that credential can authorize.
#
# Why a node-status patch rather than a device plugin: Kubernetes'
# officially documented "extended resource for node" mechanism
# (https://kubernetes.io/docs/tasks/administer-cluster/extended-resource-node/)
# is exactly this — `kubectl patch node ... --subresource=status` — for a
# resource that is a COUNTING ceiling rather than a discoverable physical device
# (there is no /dev/churn-slot to enumerate). A real device plugin would be the
# more robust choice for a multi-node cluster; see README.md "Known caveat" for
# the tradeoff and ../VALIDATION_CHECKLIST.md item 3 for confirming it survives a
# real kubelet restart.
#
# THE CAPACITY IS PROFILE DATA, NOT AN ARGUMENT. It is ADMISSION_CAPACITY_C in
# the node's profile — poweredge 32 (its CPU-throughput ceiling; see
# ../kueue/DERIVATION.md "The step back to C = 32 on the tiered host
# (2026-09-06)"), gmktec 12 (a derived first value, plan research/001 §3.5; see
# "The derivation at C = 44 — the two-node pool (2026-09-11)"). Reading it from
# the profile — the same key install-node.sh reads — is what keeps this number
# and the node's own provisioning from drifting apart, and it is why this script
# takes a PROFILE, like ../node-status-credential/provision-node-status-credential.sh
# and ../storage-sweep/install-storage-sweep.sh.
#
# THE PROFILE IS PARSED, NEVER SOURCED. It is read with `sed` for the four scalar
# keys this script needs, not through ../../phase0-bare-metal/profile.sh: the
# installed copy of this script lives at /usr/local/lib/ci-runner-k3s/ (the
# reapply unit's ExecStart target) where profile.sh is not present, so a runtime
# `source` of it would fail every five minutes. The keys read here are simple
# scalars, so a `KEY=value` extraction is sufficient and carries no dependency.
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
USAGE="usage: ${SCRIPT_NAME} PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries NODE_NAME, CLUSTER_ROLE, ADMISSION_CAPACITY_C and CHURN_KUBECONFIG_FILE)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

PROFILE="${1:?$USAGE}"
[ -f "$PROFILE" ] || die "profile not found: ${PROFILE} -- ${USAGE}"

# A scalar profile value, last occurrence wins, trailing whitespace trimmed. Not
# a sourcing: no shell expansion reaches the file's contents.
profile_value() {  # profile_value KEY
  sed -n "s/^$1=//p" "$PROFILE" | tail -n1 | sed 's/[[:space:]]*$//'
}

NODE_NAME="$(profile_value NODE_NAME)"
ROLE="$(profile_value CLUSTER_ROLE)"
CAPACITY="$(profile_value ADMISSION_CAPACITY_C)"
CHURN_KUBECONFIG_FILE="$(profile_value CHURN_KUBECONFIG_FILE)"

[ -n "$NODE_NAME" ] || die "${PROFILE}: NODE_NAME is empty -- there is no node to patch"
[[ "$CAPACITY" =~ ^[0-9]+$ ]] || die "${PROFILE}: ADMISSION_CAPACITY_C must be a non-negative integer, got '${CAPACITY}'"
case "$ROLE" in
  server|agent) ;;
  *) die "${PROFILE}: CLUSTER_ROLE must be 'server' or 'agent', got '${ROLE}'" ;;
esac

# The credential this patch authenticates with. Taken from the environment when
# the caller set it (the converge exports the admin file; a server operator may
# too); otherwise DERIVED from the role — the server's admin kubeconfig k3s
# writes at install time, or the agent's scoped node-status kubeconfig at the
# path its own profile names (never /etc/rancher/k3s/k3s.yaml, which does not
# exist on an agent). This is what lets the reapply unit carry no KUBECONFIG of
# its own and still authenticate correctly on either role.
if [ -z "${KUBECONFIG:-}" ]; then
  if [ "$ROLE" = server ]; then
    KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  else
    [ -n "$CHURN_KUBECONFIG_FILE" ] || die "${PROFILE}: CLUSTER_ROLE is 'agent' but CHURN_KUBECONFIG_FILE is empty, so there is no credential to patch node status with. Seed it with ../../secret-reinjection/seed-node-status-kubeconfig.sh first (see ../node-status-credential/README.md)."
    KUBECONFIG="$CHURN_KUBECONFIG_FILE"
  fi
fi
export KUBECONFIG
[ -f "$KUBECONFIG" ] || die "KUBECONFIG ${KUBECONFIG} not found -- $([ "$ROLE" = agent ] && printf 'seed the node-status credential (../node-status-credential/README.md)' || printf 'run ../provision-k3s.sh first')"

# ---------------------------------------------------------------------------
log "1. Wait (bounded) for node ${NODE_NAME} to register in the API, then patch it"
# At boot this service is ordered After=k3s(-agent).service, but that unit
# reaching 'active' does NOT mean the node object is registered and addressable
# yet: there is a several-second window where the API is up but `kubectl get node
# <name>` still fails. A single-shot lookup FATAL'd on every boot on the server
# (livespec plan ci-runner-pod-lifecycle-reliability, boot-2 proof 2026-09-02);
# the same window exists for an agent joining. Wait (bounded) for the named node
# to appear before patching. The FATAL is kept as the post-timeout last resort,
# so a genuinely missing node still fails loudly rather than silently patching
# nothing.
# EVERY read here is a `get --subresource=status node`, NOT a bare `get node`.
# The scoped agent credential (../node-status-credential/node-status-patch-rbac.yaml)
# grants get/patch on `nodes/status` ONLY — deliberately, so it cannot reach
# `spec` to untaint the node. A bare `kubectl get node` is a read of the parent
# `nodes` resource and would 403 on an agent, timing this loop out and never
# reaching the patch below. The status-subresource GET returns the whole Node
# object, so the readiness check and the verify jsonpath both still resolve.
#
# THE PROBE KEEPS THE API SERVER'S ANSWER, and that is the fix for
# livespec-dev-tooling-yj25uj. The probe used to be `>/dev/null 2>&1`, which
# discards the one answer that is NOT a late registration: the server REFUSING
# the credential. A poweredge-xubuntu reboot empties the tmpfs k3s datastore
# (../datastore-tmpfs/), re-creating every ServiceAccount and re-minting every
# token Secret, so an agent's previously-delivered node-status kubeconfig carries
# a token the fresh API server has never seen and every call answers "the server
# has asked for the client to provide credentials". Discarded, that read as "not
# registered": measured 2026-10-12 04:01Z-04:26Z, gmktec-xubuntu was Ready and
# registered while this unit printed "waiting for node gmktec-xubuntu to
# register..." to its timeout every five minutes and the node advertised no
# churn-slot capacity at all, so Kueue's quota was denominated in a resource no
# node offered. A rejected credential is now told apart from a missing node and
# reported as itself.
#
# MATCHED ON THE MESSAGE, not on the exit status alone: a non-zero probe can mean
# many things, and only one of them is a credential being refused. Same wording
# set the gates wrapper matches (ansible/roles/gates_kubeconfig/files/with-gates-kubeconfig),
# because it is the same API server rendering it through the same kubectl.
CREDENTIAL_REJECTED_RE='Unauthorized|asked for the client to provide credentials|You must be logged in|401'
# AND IT IS REPAIRED WITHOUT AN OPERATOR, ONCE. A rejection after a control-plane
# reboot is the EXPECTED case, not an exceptional one, so the agent re-fetches its
# credential from the server and retries rather than leaving the pool without
# churn-slot capacity until someone notices. That is the gates credential's
# pull-on-rejection pattern; the tool is the node_status_credential role's
# refresh-node-status-kubeconfig, installed beside this script.
#
# ONCE, deliberately. A retry loop would turn a genuinely revoked credential into
# an unbounded ssh hammer against the control-plane node. One refresh tells the
# expected case (a token re-minted by a boot) apart from the real one (the
# credential is gone, or the RBAC changed), and the second rejection is reported
# as itself. A SERVER is never refreshed: it authenticates as k3s's own admin
# file, which no re-mint replaces and which this script must never rewrite.
CREDENTIAL_REFRESH_BIN="${NODE_STATUS_REFRESH_BIN:-/usr/local/bin/refresh-node-status-kubeconfig}"
credential_refreshed=0
probe_stderr="$(mktemp)"
trap 'rm -f "$probe_stderr"' EXIT

NODE_WAIT_TIMEOUT="${NODE_WAIT_TIMEOUT:-120}"
deadline=$(( $(date +%s) + NODE_WAIT_TIMEOUT ))
while :; do
  kubectl get --subresource=status node "$NODE_NAME" >/dev/null 2>"$probe_stderr" && break
  if grep -qiE "$CREDENTIAL_REJECTED_RE" "$probe_stderr"; then
    cat "$probe_stderr" >&2
    echo "${SCRIPT_NAME}: the API server REJECTED the node-status credential ${KUBECONFIG} for node ${NODE_NAME} -- a rejected CREDENTIAL, not an unregistered node (the node is already there, so waiting for it to register would never end)." >&2
    [ "$credential_refreshed" -eq 0 ] || die "the API server REJECTED the node-status credential ${KUBECONFIG} for node ${NODE_NAME} AGAIN after one refresh. The credential is revoked or its RBAC changed -- re-mint it cluster-side (../node-status-credential/README.md); a second refresh would only hammer the control-plane node."
    [ "$ROLE" = agent ] || die "the API server REJECTED the node-status credential ${KUBECONFIG} for node ${NODE_NAME}, which is a '${ROLE}'. A server authenticates as k3s's own admin kubeconfig and there is nothing to re-fetch -- investigate the API server, not the credential."
    [ -x "$CREDENTIAL_REFRESH_BIN" ] || die "the API server REJECTED the node-status credential ${KUBECONFIG} for node ${NODE_NAME} and no refresh tool is executable at ${CREDENTIAL_REFRESH_BIN}, so it cannot be re-fetched here. Install it with the node_status_credential Ansible role (just ansible-apply ansible/ci-pool.yml)."
    credential_refreshed=1
    echo "${SCRIPT_NAME}: re-fetching it once via ${CREDENTIAL_REFRESH_BIN}, then retrying" >&2
    "$CREDENTIAL_REFRESH_BIN" || die "refresh FAILED (see above): ${CREDENTIAL_REFRESH_BIN} could not re-fetch the node-status credential for ${NODE_NAME}, so the rejection stands and ${KUBECONFIG} is unchanged."
    continue
  fi
  [ "$(date +%s)" -ge "$deadline" ] && die "node ${NODE_NAME} did not register in the API within ${NODE_WAIT_TIMEOUT}s"
  echo "waiting for node ${NODE_NAME} to register..."
  sleep 3
done

# ---------------------------------------------------------------------------
log "2. Patch status.capacity and status.allocatable on ${NODE_NAME} (idempotent)"
kubectl patch node "$NODE_NAME" --subresource=status --type=merge -p \
  "{\"status\":{\"capacity\":{\"ci-runner.io/churn-slot\":\"${CAPACITY}\"},\"allocatable\":{\"ci-runner.io/churn-slot\":\"${CAPACITY}\"}}}"

# ---------------------------------------------------------------------------
log "3. Verify"
kubectl get --subresource=status node "$NODE_NAME" \
  -o jsonpath='{.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}'

log "DONE. ci-runner.io/churn-slot capacity=${CAPACITY} on ${NODE_NAME} (this node only)."
