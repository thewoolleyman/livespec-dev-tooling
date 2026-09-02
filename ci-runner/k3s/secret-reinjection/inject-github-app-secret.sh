#!/usr/bin/env bash
# inject-github-app-secret.sh — (re)create the k8s Secret
# `arc-github-app-installation` in namespace `arc-runners` from 1Password,
# so a wiped/tmpfs k3s datastore comes back with the GitHub App credential
# ARC needs, with ZERO manual steps.
#
# WHY THIS EXISTS: that secret is the ONLY thing install-arc.sh will not
# create — it fails closed if the secret is absent (see ../README.md
# "Credential separation"). Until this mechanism, the secret lived ONLY in
# the k3s datastore and was created BY HAND. A datastore wipe (the coming
# tmpfs cutover, sibling item livespec-mx26zz) or any fresh cluster
# therefore lost the credential until an operator hand-recreated it. This
# script closes that disaster-recovery gap: it reconstructs the secret from
# 1Password at boot, before the reconstruct converge runs ARC.
#
# CREDENTIAL SOURCE — least-privilege, the SAME source the podman pool's
# supervisor already uses (../../gate-runner/mint-jitconfig.sh), never a
# broader fleet secret (the "Credential separation" contract). This script
# is designed to run UNDER the dedicated `github-ci-runners` 1Password
# wrapper, exactly like ../../gate-runner/gate-runner-supervisor.service:
#
#     with-github-ci-runners-env.sh -- inject-github-app-secret.sh
#
# which injects three variables from the github-ci-runners 1Password
# Environment (the App key is readable ONLY by this identity, never by a
# runner or a job):
#
#   GITHUB_APP_ID_CI_RUNNER              -> secret key github_app_id
#   GITHUB_APP_INSTALLATION_ID_CI_RUNNER -> secret key github_app_installation_id
#   GITHUB_PRIVATE_KEY_CI_RUNNER (PEM)   -> secret key github_app_private_key
#
# (These are the exact names ../../gate-runner/gate-runner-supervisor.sh
# reads out of that same injected env; this script reuses them rather than
# re-deriving.) The wrapper decrypts a systemd-creds service-account token
# and calls `op run --environment`; it draws on a SHARED daily 1Password
# quota, so this runs ONCE at boot, not on a timer.
#
# SECRET DISCIPLINE: the App private key value is NEVER echoed, logged, or
# passed as a command-line argument (which would be visible in
# /proc/<pid>/cmdline and `ps`). It is written to a mktemp file chmod 600,
# trap-cleaned on exit, and handed to kubectl via --from-file. The id
# fields (not secret-sensitive) go via --from-literal. `set -x` is NEVER
# used. Nothing but phase banners reaches stdout/stderr.
#
# Deps: kubectl (k3s-provided), a reachable k3s API (KUBECONFIG). This is a
# HOST OPERATIONAL ARTIFACT (not Python product code) — not part of
# `just check`; recreatability is the contract.
set -euo pipefail

log() { printf '\n== %s ==\n' "$*"; }

# k3s cluster kubeconfig — defaulted here and also set in the unit's
# Environment=. The invoking identity MUST be able to read this file (an
# attended-cutover precondition documented in ../README.md).
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

RUNNERS_NAMESPACE="arc-runners"
SECRET_NAME="arc-github-app-installation"

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH (k3s provides it at /usr/local/bin/kubectl)"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Verify the three credential values are present in the environment"
# Probe PRESENCE only — never the value. `printenv NAME | wc -c` reports a
# character count (0 when unset); it never prints the secret. Fail closed
# with an actionable message naming the wrapper that supplies them.
_missing=()
for _var in GITHUB_APP_ID_CI_RUNNER GITHUB_APP_INSTALLATION_ID_CI_RUNNER GITHUB_PRIVATE_KEY_CI_RUNNER; do
  if [ "$(printenv "$_var" 2>/dev/null | wc -c)" -eq 0 ]; then
    _missing+=("$_var")
  fi
done
if [ "${#_missing[@]}" -gt 0 ]; then
  cat >&2 <<EOF
FATAL: missing credential variable(s): ${_missing[*]}
This script must run UNDER the github-ci-runners 1Password wrapper, which
injects them from the dedicated github-ci-runners Environment:
  with-github-ci-runners-env.sh -- $(basename "$0")
See ../README.md "Credential separation" for the least-privilege source.
EOF
  exit 1
fi

# ---------------------------------------------------------------------------
log "1. Ensure the arc-runners namespace exists (idempotent)"
# May not exist on a genuinely fresh cluster — install-arc.sh step 2 is what
# --create-namespace's it, but this script runs BEFORE that, so create it
# here. --dry-run=client | apply is the idempotent create-or-noop.
kubectl create namespace "$RUNNERS_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
log "2. Materialize the private key to a private temp file (never argv, never logged)"
_tmpkey="$(mktemp)"
chmod 600 "$_tmpkey"
cleanup() { rm -f "$_tmpkey"; return 0; }  # never poison the exit code
trap cleanup EXIT
# printf (not echo) writes the PEM content, preserving its real newlines.
printf '%s' "$GITHUB_PRIVATE_KEY_CI_RUNNER" > "$_tmpkey"

# ---------------------------------------------------------------------------
log "3. Create/refresh the ${SECRET_NAME} secret in ${RUNNERS_NAMESPACE} (idempotent)"
# The PRIVATE KEY comes via --from-file (the temp file above), so its value
# never appears in argv. The id fields are not secret-sensitive and go via
# --from-literal. --dry-run=client | apply makes this a create-or-update.
kubectl create secret generic "$SECRET_NAME" \
  --namespace "$RUNNERS_NAMESPACE" \
  --from-literal=github_app_id="$GITHUB_APP_ID_CI_RUNNER" \
  --from-literal=github_app_installation_id="$GITHUB_APP_INSTALLATION_ID_CI_RUNNER" \
  --from-file=github_app_private_key="$_tmpkey" \
  --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
log "4. Verify the secret exists with the three expected keys (never printing values)"
# jsonpath over .data KEYS only — kubectl never emits the base64 values here.
_keys="$(kubectl get secret "$SECRET_NAME" -n "$RUNNERS_NAMESPACE" \
  -o jsonpath='{range .data.*}{"\n"}{end}' | grep -c . || true)"
[ "$_keys" -eq 3 ] || { echo "FATAL: secret ${SECRET_NAME} has ${_keys} data key(s), expected 3"; exit 1; }

log "DONE. ${RUNNERS_NAMESPACE}/${SECRET_NAME} present with 3 keys; ARC can authenticate to GitHub."
