#!/usr/bin/env bash
# inject-github-app-secret.sh — (re)create the k8s Secret
# `arc-github-app-installation` in namespace `arc-runners` from the host's
# systemd-creds LOCAL CREDSTORE, so a wiped/tmpfs k3s datastore comes back
# with the GitHub App credential ARC needs, with ZERO manual steps and NO
# network at boot.
#
# WHY THIS EXISTS: that secret is the ONLY thing install-arc.sh will not
# create — it fails closed if the secret is absent (see ../README.md
# "Credential separation"). Until this mechanism, the secret lived ONLY in
# the k3s datastore and was created BY HAND. A datastore wipe (the coming
# tmpfs cutover, sibling item livespec-mx26zz) or any fresh cluster
# therefore lost the credential until an operator hand-recreated it. This
# script closes that disaster-recovery gap: it reconstructs the secret from
# host-encrypted local credentials at boot, before the reconstruct converge
# runs ARC.
#
# CREDENTIAL SOURCE — the host systemd credstore, decrypted locally as ROOT.
# The three App values are stored host-encrypted under
# /etc/credstore.encrypted/ (seeded once, attended, by the maintainer via
# seed-github-app-creds.sh — the ONLY step that touches 1Password). This
# unit runs as ROOT and its systemd `LoadCredentialEncrypted=` lines decrypt
# them into $CREDENTIALS_DIRECTORY (root-only, mode 0400) at start — NO
# `op run`, NO 1Password wrapper, NO ci-sup identity, NO network. That is
# why the model changed from the op-run/wrapper path: `op run` refuses to
# run as root, and no ci-sup identity exists on this host.
#
# The three credentials arrive in $CREDENTIALS_DIRECTORY under these names,
# mapping onto the secret's three data keys:
#
#   arc-github-app-id              -> secret key github_app_id
#   arc-github-app-installation-id -> secret key github_app_installation_id
#   arc-github-app-private-key     -> secret key github_app_private_key  (PEM)
#
# SECRET DISCIPLINE: the App private key value is NEVER echoed, logged, or
# passed as a command-line argument. It already IS a root-only private file
# in $CREDENTIALS_DIRECTORY, so it is handed to kubectl via --from-file
# straight from that path (never --from-literal / argv, never a copy). The
# id fields (not secret-sensitive) go via --from-literal. `set -x` is NEVER
# used. Nothing but phase banners reaches stdout/stderr.
#
# Deps: kubectl (k3s-provided), a reachable k3s API (KUBECONFIG). This is a
# HOST OPERATIONAL ARTIFACT (not Python product code) — not part of
# `just check`; recreatability is the contract.
set -euo pipefail

log() { printf '\n== %s ==\n' "$*"; }

# k3s cluster kubeconfig — defaulted here and also set in the unit's
# Environment=. This unit runs as root, so it reads the default 0600
# root:root kubeconfig directly.
export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

RUNNERS_NAMESPACE="arc-runners"
SECRET_NAME="arc-github-app-installation"

# systemd populates $CREDENTIALS_DIRECTORY for a unit that declares
# LoadCredentialEncrypted=/ImportCredential=. Absent it, this script was not
# launched by its unit — fail closed rather than guess a path.
CRED_DIR="${CREDENTIALS_DIRECTORY:?CREDENTIALS_DIRECTORY unset — run this via inject-github-app-secret.service (its LoadCredentialEncrypted= lines populate it), not by hand}"
APP_ID_CRED="${CRED_DIR}/arc-github-app-id"
INSTALLATION_ID_CRED="${CRED_DIR}/arc-github-app-installation-id"
PRIVATE_KEY_CRED="${CRED_DIR}/arc-github-app-private-key"

command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH (k3s provides it at /usr/local/bin/kubectl)"; exit 1; }

# ---------------------------------------------------------------------------
log "0. Verify the three decrypted credential files are present"
# Fail closed with an actionable message naming the seed step if any cred is
# missing (never printing a value). A missing file here means the credstore
# was never seeded (or a name drifted).
_missing=()
for _f in "$APP_ID_CRED" "$INSTALLATION_ID_CRED" "$PRIVATE_KEY_CRED"; do
  [ -r "$_f" ] || _missing+=("$(basename "$_f")")
done
if [ "${#_missing[@]}" -gt 0 ]; then
  cat >&2 <<EOF
FATAL: missing decrypted credential(s): ${_missing[*]}
The host credstore was not seeded (or a credential name drifted). Run the
attended seed step first (maintainer, in the github-ci-runners group):
  with-github-ci-runners-env.sh -- .../secret-reinjection/seed-github-app-creds.sh
See ../README.md "Credential separation".
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
log "2. Create/refresh the ${SECRET_NAME} secret in ${RUNNERS_NAMESPACE} (idempotent)"
# The PRIVATE KEY comes via --from-file, pointing straight at the root-only
# decrypted credential file — its value never appears in argv and is never
# copied. The id fields are not secret-sensitive and go via --from-literal
# (command substitution strips the trailing newline). --dry-run=client |
# apply makes this a create-or-update.
kubectl create secret generic "$SECRET_NAME" \
  --namespace "$RUNNERS_NAMESPACE" \
  --from-literal=github_app_id="$(cat "$APP_ID_CRED")" \
  --from-literal=github_app_installation_id="$(cat "$INSTALLATION_ID_CRED")" \
  --from-file=github_app_private_key="$PRIVATE_KEY_CRED" \
  --dry-run=client -o yaml | kubectl apply -f -

# ---------------------------------------------------------------------------
log "3. Verify the secret exists with the three expected keys (never printing values)"
# go-template `len .data` counts the KEYS only — kubectl never emits the
# base64 values here. (The earlier `jsonpath='{range .data.*}{"\n"}{end}' |
# grep -c .` form was wrong by construction: it emitted one EMPTY line per
# key and `grep -c .` counts NON-empty lines, so it read 0 on every run —
# caught by the first k3s-restart cutover test, 2026-09-02, where the secret
# was correctly rebuilt with 3 keys while this check reported failure.)
# `|| echo 0` keeps `_keys` numeric if the get fails, so the `-eq` below
# fails closed instead of erroring on an empty string.
_keys="$(kubectl get secret "$SECRET_NAME" -n "$RUNNERS_NAMESPACE" \
  -o go-template='{{len .data}}' 2>/dev/null || echo 0)"
[ "$_keys" -eq 3 ] || { echo "FATAL: secret ${SECRET_NAME} has ${_keys} data key(s), expected 3"; exit 1; }

log "DONE. ${RUNNERS_NAMESPACE}/${SECRET_NAME} present with 3 keys; ARC can authenticate to GitHub."
