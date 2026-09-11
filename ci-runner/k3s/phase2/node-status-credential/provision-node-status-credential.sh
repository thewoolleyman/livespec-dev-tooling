#!/usr/bin/env bash
# provision-node-status-credential.sh — the CLUSTER-SIDE converge that produces
# an AGENT node's churn-slot credential: it applies ./node-status-patch-rbac.yaml
# for one named node (a per-node ServiceAccount plus a ClusterRole holding
# exactly `get`+`patch` on that node's `nodes/status`), and then renders the
# per-node KUBECONFIG that ServiceAccount authenticates with.
#
# WHAT IT FIXES. ../node-extended-resource/reapply-node-extended-resource.service
# patches node status through the API, and on a server its patch script
# authenticates as the k3s SERVER's admin file `/etc/rancher/k3s/k3s.yaml`. That
# file does not exist on an agent, so a node-local churn-slot timer on an agent
# has no credential at all; nothing under ci-runner/ minted one, and nothing
# placed one. Found by the first dry-run of the rebuild recipe on gmktec-xubuntu,
# 2026-09-06 (livespec-dev-tooling-xa6o). This script is the minting half;
# ../../secret-reinjection/seed-node-status-kubeconfig.sh is the delivery half,
# and R5 wired the consumer (an agent's reapply timer reads the delivered
# kubeconfig) — see ./README.md.
#
# WHERE IT RUNS, AND WHY NOT ON THE AGENT. On the k3s SERVER, as the maintainer,
# with the admin KUBECONFIG — because creating RBAC and reading a token Secret
# are cluster-admin acts. The node it provisions FOR is named by the PROFILE
# argument, never by the host it runs on: an agent that could mint its own
# credential would not need one. Read ./README.md before the first live run.
#
# THE ARGUMENT IS A PROFILE, NOT A NODE NAME. Everything this script needs is
# already node DATA — NODE_NAME names the node the grant is scoped to,
# CLUSTER_JOIN_ADDRESS is the API endpoint the agent can actually reach (the
# admin file's own `server:` is the SERVER's view and may be a loopback address
# the agent cannot use), and CHURN_KUBECONFIG_FILE is where the rendered
# credential is destined. Reading them through the shared
# ../../phase0-bare-metal/profile.sh parser is what keeps this script and the
# node's own provisioning from drifting apart.
#
# SECRET DISCIPLINE. The rendered kubeconfig carries a bearer token. It is never
# echoed, never logged and never placed on argv: it flows from `kubectl` into a
# shell variable and out through `install -m 0600 /dev/stdin`, so it exists on
# disk only as an owner-only file. `--dry-run` requires no cluster and reads no
# credential, which is what makes the whole plan — including the exact RBAC
# bytes — reviewable before anything is minted, and what lets
# ./provision-node-status-credential-exit-tests.sh assert this off-host.
#
# IDEMPOTENT. The RBAC apply is `kubectl apply --dry-run=client -o yaml -f - |
# kubectl apply -f -`, the fleet's converge shape: the first stage validates and
# defaults every object LOCALLY, so a malformed render is rejected before any
# object reaches the cluster rather than half-applied mid-stream. Re-running
# changes nothing when the cluster already matches. The token Secret is
# populated by the token controller, so a re-run renders the SAME token rather
# than rotating it; rotation is `kubectl delete secret` followed by a re-run,
# and it is deliberately not a flag here.
#
# Usage: provision-node-status-credential.sh [--dry-run] [--render-to PATH] PROFILE
#   PROFILE      path to the node's phase0-bare-metal/profiles/<node>.env
#   --render-to  write the rendered kubeconfig to PATH (mode 0600). Omit it to
#                converge the RBAC only. Refused under --dry-run: a plan that
#                touched nothing cannot have produced a credential.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
K3S_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)"
SCRIPT_NAME="$(basename "$0")"

RBAC_TEMPLATE="${SCRIPT_DIR}/node-status-patch-rbac.yaml"
PLACEHOLDER="NODE_NAME_PLACEHOLDER"
NAMESPACE="ci-runner-node-status"
SA_PREFIX="node-status-patcher-"

# The mode the rendered kubeconfig is written with, here and on the node: a
# bearer token is owner-only or it is not a secret.
RENDER_MODE="0600"

# How long to wait for the token controller to populate the Secret. It is
# normally sub-second; the wait exists because the Secret is created by THIS
# run, and reading it in the same breath is a race the converge would otherwise
# lose on a cold API server.
TOKEN_WAIT_TIMEOUT="${TOKEN_WAIT_TIMEOUT:-60}"

USAGE="usage: ${SCRIPT_NAME} [--dry-run] [--render-to PATH] PROFILE   (PROFILE = phase0-bare-metal/profiles/<node>.env, which carries NODE_NAME, CLUSTER_ROLE, CLUSTER_JOIN_ADDRESS and CHURN_KUBECONFIG_FILE)"

die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }
log() { printf '\n== %s ==\n' "$*"; }

# ---------------------------------------------------------------------------
# Command line
# ---------------------------------------------------------------------------
DRY_RUN=0
RENDER_TO=""
RENDER_TO_GIVEN=0
PROFILE_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    --render-to)
      [ $# -ge 2 ] || die "--render-to needs a value -- ${USAGE}"
      [ -n "$2" ] || die "--render-to needs a value -- ${USAGE}"
      [ "$RENDER_TO_GIVEN" -eq 0 ] || die "--render-to given more than once -- ${USAGE}"
      RENDER_TO_GIVEN=1
      RENDER_TO="$2"; shift ;;
    -h|--help) printf '%s\n' "$USAGE"; exit 0 ;;
    # No `--` end-of-options case, for the same reason the sibling seed scripts
    # have none: it would only be a way to silently swallow what follows it.
    -*) die "unknown option '$1' -- ${USAGE}" ;;
    *)
      if [ -n "$PROFILE_ARG" ]; then
        die "more than one profile given ('${PROFILE_ARG}' and '$1') -- ${USAGE}"
      fi
      PROFILE_ARG="$1" ;;
  esac
  shift
done

[ -n "$PROFILE_ARG" ] || die "no profile given -- ${USAGE}"

# A dry run mutates nothing, so it cannot have written a credential either.
# Refused rather than ignored: silently dropping the flag is how an operator
# ends up believing a file exists that does not.
if [ "$DRY_RUN" -eq 1 ] && [ "$RENDER_TO_GIVEN" -eq 1 ]; then
  die "--render-to and --dry-run are mutually exclusive: a dry run mints no token, so it has nothing to write to '${RENDER_TO}'"
fi

[ -f "$RBAC_TEMPLATE" ] || die "RBAC template not found: ${RBAC_TEMPLATE}"

# ---------------------------------------------------------------------------
# Profile: parsed, never sourced, through the SAME parser the node's own
# provisioning reads these keys with.
# ---------------------------------------------------------------------------
# shellcheck source=ci-runner/k3s/phase0-bare-metal/profile.sh
source "${K3S_DIR}/phase0-bare-metal/profile.sh"
profile_load "$PROFILE_ARG"

NODE_NAME="${CFG[NODE_NAME]}"
ROLE="${CFG[CLUSTER_ROLE]}"
API_SERVER="${CFG[CLUSTER_JOIN_ADDRESS]}"
TARGET_PATH="${CFG[CHURN_KUBECONFIG_FILE]}"

# A SERVER needs none of this and must not be given it: it already patches node
# status through /etc/rancher/k3s/k3s.yaml, the admin file it writes at install
# time. Minting a second, narrower credential for a machine that holds the
# unrestricted one is not a narrowing — it is one more long-lived token to keep
# track of. Refused in --dry-run too: the role is profile DATA, so a plan for a
# run that could never be executed must not be printed as though it could.
[ "$ROLE" = agent ] || die "${PROFILE_ARG}: CLUSTER_ROLE is '${ROLE}', not 'agent'. Only an agent lacks a node-status credential; a server patches node status through its own /etc/rancher/k3s/k3s.yaml. Nothing was applied."

# The destination is what makes the rendered credential deliverable, and it is
# the node's DATA rather than this script's constant. Without it there is a
# credential and nowhere agreed to put it, which is exactly the split this
# artifact exists to close.
[ -n "$TARGET_PATH" ] || die "${PROFILE_ARG}: CHURN_KUBECONFIG_FILE is empty, so this node names no path for the rendered kubeconfig. Set it to the path the node-local churn-slot timer will read (never /etc/rancher/k3s/k3s.yaml, which is the SERVER's admin file and does not exist on an agent). Nothing was applied."

# The agent reaches the API at the address its own profile joins on. The admin
# file's `server:` is the SERVER's view of itself and is routinely a loopback
# address, which would render a kubeconfig the agent cannot use.
[ -n "$API_SERVER" ] || die "${PROFILE_ARG}: CLUSTER_JOIN_ADDRESS is empty, so there is no API endpoint to render into the kubeconfig. Nothing was applied."

SA_NAME="${SA_PREFIX}${NODE_NAME}"
SECRET_NAME="${SA_NAME}"

# ---------------------------------------------------------------------------
# The render. Substituted HERE, once, into a variable both the plan and the
# apply read, so the bytes a dry run prints are the bytes a live run applies.
# `|` as the sed delimiter and a node name constrained to a DNS label by
# Kubernetes itself: a name carrying `|` could not be a node name.
# ---------------------------------------------------------------------------
RENDERED_RBAC="$(sed "s|${PLACEHOLDER}|${NODE_NAME}|g" "$RBAC_TEMPLATE")"

# Fail loudly rather than applying a grant bound to a node that does not exist.
if printf '%s' "$RENDERED_RBAC" | grep -q "$PLACEHOLDER"; then
  die "${PLACEHOLDER} survived substitution in the rendered ${RBAC_TEMPLATE}"
fi

print_plan() {
  printf '== %s plan ==\n' "$SCRIPT_NAME"
  printf 'profile:    %s\n' "$PROFILE_ARG"
  printf 'node:       %s\n' "$NODE_NAME"
  printf 'role:       %s\n' "$ROLE"
  printf 'api:        %s (the address the AGENT joins on, not the admin file server: field)\n' "$API_SERVER"
  printf 'namespace:  %s\n' "$NAMESPACE"
  printf 'account:    %s\n' "$SA_NAME"
  printf 'grant:      get,patch on nodes/status, resourceNames=[%s] -- and nothing else\n' "$NODE_NAME"
  printf 'destination: %s (CHURN_KUBECONFIG_FILE; the seed script places it there, this script does not)\n' "$TARGET_PATH"
  if [ "$RENDER_TO_GIVEN" -eq 1 ]; then
    printf 'render-to:  %s (mode %s; the token never reaches an argv or a log)\n' "$RENDER_TO" "$RENDER_MODE"
  else
    printf 'render-to:  (not given -- the RBAC is converged and NO kubeconfig is rendered)\n'
  fi
  printf 'apply:      kubectl apply --dry-run=client -o yaml -f - | kubectl apply -f -   (idempotent; re-running changes nothing)\n'
}

print_plan

log "The rendered RBAC, in full -- these are the exact bytes that would be applied"
printf '%s\n' "$RENDERED_RBAC"

# ---------------------------------------------------------------------------
# --dry-run stops here, having touched nothing and having needed no cluster.
# That is the point: the operator reviewing the grant above is deciding WHETHER
# to mint it, so the review must be possible without the power to mint it.
# ---------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 1 ]; then
  printf '\n-- --dry-run: the plan above was printed and NOTHING was executed --\n'
  exit 0
fi

command -v kubectl >/dev/null || die "kubectl not found on PATH, and this converge is a cluster-side act"
# No apostrophe in the message below, deliberately: a `'` inside a `${VAR:?...}`
# word breaks quote parity for shellcheck and it mis-parses the rest of the
# file (SC1078/SC1089), which is a real cost for a possessive.
: "${KUBECONFIG:?set KUBECONFIG to the k3s SERVER admin kubeconfig (/etc/rancher/k3s/k3s.yaml). This converge CREATES the narrow credential an agent uses; it is itself a cluster-admin act and runs on the server.}"

# ---------------------------------------------------------------------------
log "1. Converge the per-node RBAC (Namespace, ServiceAccount, token Secret, ClusterRole, ClusterRoleBinding)"
printf '+ kubectl apply --dry-run=client -o yaml -f - | kubectl apply -f -\n'
printf '%s\n' "$RENDERED_RBAC" | kubectl apply --dry-run=client -o yaml -f - | kubectl apply -f -

if [ "$RENDER_TO_GIVEN" -eq 0 ]; then
  log "DONE. RBAC converged for ${NODE_NAME}. No kubeconfig was rendered (no --render-to given)."
  printf 'Next: re-run with --render-to PATH to mint the kubeconfig, then see ./README.md for delivery.\n'
  exit 0
fi

# ---------------------------------------------------------------------------
log "2. Wait (bounded) for the token controller to populate ${SECRET_NAME}"
# The Secret is created by step 1, so on a cold API server it exists with an
# empty `data` for a moment. A single-shot read would render a kubeconfig with
# an empty token -- a file that looks right and authenticates as nobody, which
# is the failure shape this whole item exists to stop repeating.
deadline=$(( $(date +%s) + TOKEN_WAIT_TIMEOUT ))
SA_TOKEN=""
CA_DATA=""
while :; do
  SA_TOKEN="$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.token}' 2>/dev/null || true)"
  CA_DATA="$(kubectl get secret "$SECRET_NAME" -n "$NAMESPACE" -o jsonpath='{.data.ca\.crt}' 2>/dev/null || true)"
  [ -n "$SA_TOKEN" ] && [ -n "$CA_DATA" ] && break
  [ "$(date +%s)" -ge "$deadline" ] && die "the token controller did not populate secret/${SECRET_NAME} in ${NAMESPACE} within ${TOKEN_WAIT_TIMEOUT}s. Nothing was rendered; the RBAC from step 1 is applied and re-running is safe."
  printf 'waiting for secret/%s to be populated...\n' "$SECRET_NAME"
  sleep 2
done

# Decoded through a pipe, never through an argument: `base64 -d` on argv would
# put the token in /proc for anything on the host to read.
SA_TOKEN="$(printf '%s' "$SA_TOKEN" | base64 -d)"
[ -n "$SA_TOKEN" ] || die "secret/${SECRET_NAME} carries an EMPTY token after decoding. Nothing was rendered."

# ---------------------------------------------------------------------------
log "3. Render the kubeconfig to ${RENDER_TO} (mode ${RENDER_MODE})"
# `certificate-authority-data` is passed through STILL base64-encoded, which is
# the encoding the kubeconfig format wants -- decoding and re-encoding it would
# be two chances to corrupt a certificate for no gain. The heredoc reaches
# `install` over /dev/stdin, so neither the token nor the CA is ever an argv.
install -m "$RENDER_MODE" /dev/stdin "$RENDER_TO" <<KUBECONFIG_EOF
apiVersion: v1
kind: Config
clusters:
  - name: ci-runner
    cluster:
      server: ${API_SERVER}
      certificate-authority-data: ${CA_DATA}
users:
  - name: ${SA_NAME}
    user:
      token: ${SA_TOKEN}
contexts:
  - name: ${SA_NAME}@ci-runner
    context:
      cluster: ci-runner
      user: ${SA_NAME}
current-context: ${SA_NAME}@ci-runner
KUBECONFIG_EOF

log "DONE. ${NODE_NAME}'s node-status credential is minted."
printf 'rendered: %s (%s) -- it grants get+patch on nodes/status for %s and nothing else.\n' \
  "$RENDER_TO" "$RENDER_MODE" "$NODE_NAME"
printf 'Next: store its CONTENTS in the github-ci-runners 1Password Environment as\n'
printf '      K3S_NODE_STATUS_KUBECONFIG_CI_RUNNER, delete %s from this server, and run\n' "$RENDER_TO"
printf '      ../../secret-reinjection/seed-node-status-kubeconfig.sh ON THE AGENT to place it\n'
printf '      at %s. See ./README.md.\n' "$TARGET_PATH"
