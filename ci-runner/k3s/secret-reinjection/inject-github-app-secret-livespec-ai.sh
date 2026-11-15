#!/usr/bin/env bash
# inject-github-app-secret-livespec-ai.sh — the ORGANIZATION projection of the
# ARC secret reinjection (livespec-dev-tooling-h5r75q). It writes the
# `livespec-ai-arc` GitHub App credential into the k8s Secret
# `arc-github-app-installation-livespec-ai` in namespace `arc-runners`, the
# Secret the scale sets registered at the `livespec-ai` organization
# authenticate with. The personal-account Secret `arc-github-app-installation`
# is the sibling inject-github-app-secret.sh's, and this script never names it.
#
# Governing text: SPECIFICATION/non-functional-requirements.md §"Runner-pool
# node rebuild recipe", paragraph "ARC GitHub App credentials, one Secret per
# account.", and its two `## Scenario: the ARC secret reinjection ...`
# scenarios in SPECIFICATION/scenarios.md.
#
# CREDENTIAL SOURCE — the ENVIRONMENT, and nothing else. This script is the
# child of homelab's shared-credentials launcher, run as the runtime manifest
# consumer `livespec-ai-arc`:
#
#   sudo -n /usr/bin/python3 -I .../shared-credentials-0.3.0.pyz launch \
#     --manifest /etc/livespec-ci-credentials/<host>.json \
#     --consumer livespec-ai-arc -- <this script>
#
# The launcher reads the three AWS SSM parameters under
# /gitops/v1/shared/providers/github/livespec-ai-arc/ at launch and hands them
# over ONLY as LIVESPEC_AI_ARC_APP_ID, LIVESPEC_AI_ARC_INSTALLATION_ID and
# LIVESPEC_AI_ARC_PRIVATE_KEY (the PEM as issued). No systemd credential, no
# $CREDENTIALS_DIRECTORY, and nothing sealed on the host: only the host's
# bootstrap key is sealed there, and only the launcher (as root) opens it.
#
# WHO RUNS IT — a dedicated NON-ROOT user, `arc-org-projector`. The launcher
# refuses a root child (it drops to SUDO_UID), so this is not optional. That
# user's Kubernetes identity is a client certificate (CN=arc-org-projector, no
# group) whose kubeconfig ensure-arc-org-projector-access.sh renders, and whose
# whole grant is arc-org-projector-rbac.yaml: get, update, patch on THIS ONE
# Secret by resourceNames, and nothing else — so it can neither read nor write
# arc-github-app-installation or any other Secret. Because a Role cannot
# name-scope `create`, that privileged step also creates the empty placeholder
# Secret this script then REPLACES. See ensure-arc-org-projector-access.sh for
# why the identity is a certificate and not a ServiceAccount (the datastore is
# tmpfs).
#
# FAILURE — every missing or EMPTY variable is named, the script exits 1, and
# it does so before the first kubectl call, so the org Secret is left exactly
# as it was.
#
# SECRET DISCIPLINE — no value is ever printed, logged or put on a command line,
# in failure or in success. All three values reach kubectl through
# `--from-file=<key>=<(printf '%s' "$VAR")`: printf is a bash builtin (no
# exec, so no argv in /proc), and kubectl's argv carries only a /dev/fd path.
# The rendered Secret flows over a pipe into `kubectl replace -f -`. `set -x`
# is never used. Nothing but phase banners and key COUNTS reach stdout/stderr.
#
# WHY `replace`, NOT `apply`. `replace` is one PUT (the `update` verb) on the
# named object, which the narrow grant allows. `apply` would also stamp a
# last-applied annotation holding the whole object, values included.
#
# Deps: kubectl (k3s-provided at /usr/local/bin, on the launcher's child PATH).
# A HOST OPERATIONAL ARTIFACT, not Python product code. Its off-host proof is
# tests/consumer/test_arc_org_secret_projection_scenarios.py.
set -euo pipefail

log() { printf '\n== %s ==\n' "$*"; }

# The launcher builds the child environment from scratch (PATH and HOME only,
# plus the three values), so the kubeconfig path is this script's default, not
# something the unit can pass through.
export KUBECONFIG="${ARC_ORG_PROJECTOR_KUBECONFIG:-/etc/arc-org-projector/kubeconfig}"

RUNNERS_NAMESPACE="arc-runners"
SECRET_NAME="arc-github-app-installation-livespec-ai"

# ---------------------------------------------------------------------------
log "0. Verify the launcher supplied all three livespec-ai-arc values"
# `${!name:-}` reads each variable by NAME; only the name is ever printed.
_missing=()
for _name in LIVESPEC_AI_ARC_APP_ID LIVESPEC_AI_ARC_INSTALLATION_ID LIVESPEC_AI_ARC_PRIVATE_KEY; do
  [ -n "${!_name:-}" ] || _missing+=("$_name")
done
if [ "${#_missing[@]}" -gt 0 ]; then
  for _name in "${_missing[@]}"; do
    printf 'FATAL: %s is missing or empty\n' "$_name" >&2
  done
  printf 'FATAL: %d of 3 livespec-ai-arc value(s) missing (%s); the launcher could not read the matching SSM parameter(s) under /gitops/v1/shared/providers/github/livespec-ai-arc/. Secret %s/%s was NOT changed.\n' \
    "${#_missing[@]}" "${_missing[*]}" "$RUNNERS_NAMESPACE" "$SECRET_NAME" >&2
  exit 1
fi

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH (k3s provides it at /usr/local/bin/kubectl)" >&2; exit 1; }

# ---------------------------------------------------------------------------
log "1. Replace ${RUNNERS_NAMESPACE}/${SECRET_NAME} with the livespec-ai-arc credential"
kubectl create secret generic "$SECRET_NAME" \
  --namespace "$RUNNERS_NAMESPACE" \
  --from-file=github_app_id=<(printf '%s' "$LIVESPEC_AI_ARC_APP_ID") \
  --from-file=github_app_installation_id=<(printf '%s' "$LIVESPEC_AI_ARC_INSTALLATION_ID") \
  --from-file=github_app_private_key=<(printf '%s' "$LIVESPEC_AI_ARC_PRIVATE_KEY") \
  --dry-run=client -o yaml | kubectl replace -f - >/dev/null

# ---------------------------------------------------------------------------
log "2. Verify the secret carries the three expected keys (never printing values)"
# go-template `len .data` counts KEYS only; no value is emitted. `|| echo 0`
# keeps the comparison numeric, so a failed read fails closed.
_keys="$(kubectl get secret "$SECRET_NAME" -n "$RUNNERS_NAMESPACE" \
  -o go-template='{{len .data}}' 2>/dev/null || echo 0)"
[ "$_keys" -eq 3 ] || { echo "FATAL: secret ${SECRET_NAME} has ${_keys} data key(s), expected 3" >&2; exit 1; }

log "DONE. ${RUNNERS_NAMESPACE}/${SECRET_NAME} carries the livespec-ai-arc App credential (3 keys)."
