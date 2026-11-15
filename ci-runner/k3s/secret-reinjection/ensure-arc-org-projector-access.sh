#!/usr/bin/env bash
# ensure-arc-org-projector-access.sh — the PRIVILEGED half of the organization
# projection (livespec-dev-tooling-h5r75q). It runs as root, with the k3s admin
# kubeconfig, as the `ExecStartPre=+` of
# inject-github-app-secret-livespec-ai.service, before the unprivileged
# projection (inject-github-app-secret-livespec-ai.sh) runs as
# `arc-org-projector`. It reads and writes NO credential value of the
# livespec-ai-arc App: those exist only in the launcher's child environment.
#
# THE IDENTITY DESIGN, and why it is a client certificate.
#
#   The k3s datastore is on TMPFS, so every reboot deletes every cluster object:
#   a ServiceAccount, its token Secret, a Role, a RoleBinding. A ServiceAccount
#   token in a node-side kubeconfig would therefore authenticate as nobody after
#   the first reboot. The k3s CLIENT CA (/var/lib/rancher/k3s/server/tls/
#   client-ca.{crt,key}) lives on disk and survives, and the API server
#   authenticates any certificate it signed as User=<CN>, Groups=<O>. So:
#
#   1. The user `arc-org-projector` is a client certificate, CN=arc-org-projector
#      with NO organization (no group beyond system:authenticated), EKU
#      clientAuth, signed here by that CA. Its kubeconfig lives at
#      /etc/arc-org-projector/kubeconfig, root:arc-org-projector 0640, readable
#      by that one host user and by root. It is re-minted only when absent, no
#      longer verifying against the current client CA, or within 30 days of
#      expiry.
#   2. Its grant, arc-org-projector-rbac.yaml (a Role and RoleBinding in
#      arc-runners: get, update, patch on Secret
#      arc-github-app-installation-livespec-ai by resourceNames), is re-applied
#      here on every run, because the reboot erased it.
#   3. RBAC cannot name-scope `create`, so the projection cannot create its own
#      Secret. This step creates it EMPTY when it is absent, and never touches
#      it when it exists, so a failed projection leaves the last good value.
#   4. The grant is then READ BACK by impersonation: the user must be able to
#      update its Secret, and must NOT be able to get the personal-account
#      Secret arc-github-app-installation or list Secrets. A wider grant fails
#      the unit before the projection runs.
#
# The certificate's private key is a node-local identity, not one of the three
# livespec-ai-arc values, and it is written only into the 0640 kubeconfig via
# a private mktemp -d (never argv, never printed).
#
# Deps: kubectl, openssl, a reachable k3s API. A HOST OPERATIONAL ARTIFACT.
set -euo pipefail

log() { printf '\n== %s ==\n' "$*"; }
die() { printf 'FATAL: %s\n' "$*" >&2; exit 1; }

export KUBECONFIG="${KUBECONFIG:-/etc/rancher/k3s/k3s.yaml}"

PROJECTOR_USER="${ARC_ORG_PROJECTOR_USER:-arc-org-projector}"
PROJECTOR_DIR="${ARC_ORG_PROJECTOR_DIR:-/etc/arc-org-projector}"
PROJECTOR_KUBECONFIG="${PROJECTOR_DIR}/kubeconfig"
PROJECTOR_CERT="${PROJECTOR_DIR}/client.crt"
K3S_TLS_DIR="${K3S_TLS_DIR:-/var/lib/rancher/k3s/server/tls}"
CLIENT_CA_CRT="${K3S_TLS_DIR}/client-ca.crt"
CLIENT_CA_KEY="${K3S_TLS_DIR}/client-ca.key"
SERVER_CA_CRT="${K3S_TLS_DIR}/server-ca.crt"
RBAC_FILE="${ARC_ORG_PROJECTOR_RBAC:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/arc-org-projector-rbac.yaml}"
CERT_DAYS=365
RENEW_SECONDS=$((30 * 24 * 3600))

RUNNERS_NAMESPACE="arc-runners"
SECRET_NAME="arc-github-app-installation-livespec-ai"
PERSONAL_SECRET_NAME="arc-github-app-installation"

[ "$(id -u)" -eq 0 ] || die "run as root (the unit's ExecStartPre=+): it signs with the k3s client CA and uses the admin kubeconfig"
command -v kubectl >/dev/null || die "kubectl not found on PATH"
command -v openssl >/dev/null || die "openssl not found on PATH"
[ -f "$RBAC_FILE" ] || die "RBAC file not found: ${RBAC_FILE}"
[ -d "$PROJECTOR_DIR" ] || die "${PROJECTOR_DIR} is missing; the secret_reinjection role creates it (root:${PROJECTOR_USER} 0750)"
for _f in "$CLIENT_CA_CRT" "$CLIENT_CA_KEY" "$SERVER_CA_CRT"; do
  [ -r "$_f" ] || die "k3s CA file not readable: ${_f}"
done

# ---------------------------------------------------------------------------
log "1. Ensure the ${RUNNERS_NAMESPACE} namespace, the projector's Role and RoleBinding"
kubectl create namespace "$RUNNERS_NAMESPACE" --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -f "$RBAC_FILE"

# ---------------------------------------------------------------------------
log "2. Ensure the placeholder ${RUNNERS_NAMESPACE}/${SECRET_NAME} exists (created EMPTY only when absent)"
if kubectl get secret "$SECRET_NAME" -n "$RUNNERS_NAMESPACE" -o name >/dev/null 2>&1; then
  printf '%s/%s present; left unchanged\n' "$RUNNERS_NAMESPACE" "$SECRET_NAME"
else
  kubectl create secret generic "$SECRET_NAME" -n "$RUNNERS_NAMESPACE"
fi

# ---------------------------------------------------------------------------
log "3. Ensure ${PROJECTOR_USER}'s client certificate kubeconfig"
_current=0
if [ -s "$PROJECTOR_KUBECONFIG" ] && [ -s "$PROJECTOR_CERT" ] \
  && openssl verify -CAfile "$CLIENT_CA_CRT" "$PROJECTOR_CERT" >/dev/null 2>&1 \
  && openssl x509 -in "$PROJECTOR_CERT" -noout -checkend "$RENEW_SECONDS" >/dev/null 2>&1; then
  _current=1
fi
if [ "$_current" -eq 1 ]; then
  printf 'kubeconfig current (verifies against the client CA, more than 30 days left); not re-minted\n'
else
  _server="$(kubectl config view --raw -o jsonpath='{.clusters[0].cluster.server}')"
  [ -n "$_server" ] || die "could not read the API server URL from the admin kubeconfig"
  _work="$(umask 077 && mktemp -d)"
  trap 'rm -rf -- "${_work}"' EXIT
  (
    umask 077
    openssl req -new -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
      -keyout "${_work}/client.key" -subj "/CN=${PROJECTOR_USER}" -out "${_work}/client.csr" 2>/dev/null
    printf 'keyUsage=critical,digitalSignature\nextendedKeyUsage=clientAuth\n' > "${_work}/ext"
    openssl x509 -req -in "${_work}/client.csr" -CA "$CLIENT_CA_CRT" -CAkey "$CLIENT_CA_KEY" \
      -set_serial "0x$(openssl rand -hex 16)" -days "$CERT_DAYS" -sha256 \
      -extfile "${_work}/ext" -out "${_work}/client.crt" 2>/dev/null
    _kc="${_work}/kubeconfig"
    kubectl config set-cluster ci-runner --kubeconfig "$_kc" --server "$_server" \
      --certificate-authority "$SERVER_CA_CRT" --embed-certs=true >/dev/null
    kubectl config set-credentials "$PROJECTOR_USER" --kubeconfig "$_kc" \
      --client-certificate "${_work}/client.crt" --client-key "${_work}/client.key" --embed-certs=true >/dev/null
    kubectl config set-context "${PROJECTOR_USER}@ci-runner" --kubeconfig "$_kc" \
      --cluster ci-runner --user "$PROJECTOR_USER" >/dev/null
    kubectl config use-context "${PROJECTOR_USER}@ci-runner" --kubeconfig "$_kc" >/dev/null
  )
  # Same-directory temp + rename: atomic, and never readable beyond its owner
  # and group (uutils `install` refuses an existing destination; see
  # ../phase2/node-status-credential/provision-node-status-credential.sh).
  _tmp="$(umask 077 && mktemp "${PROJECTOR_KUBECONFIG}.XXXXXX")"
  cat "${_work}/kubeconfig" > "$_tmp"
  chown "root:${PROJECTOR_USER}" "$_tmp"
  chmod 0640 "$_tmp"
  mv -f "$_tmp" "$PROJECTOR_KUBECONFIG"
  _tmp="$(mktemp "${PROJECTOR_CERT}.XXXXXX")"
  cat "${_work}/client.crt" > "$_tmp"
  chmod 0644 "$_tmp"
  mv -f "$_tmp" "$PROJECTOR_CERT"
  printf 'minted CN=%s, valid %d days\n' "$PROJECTOR_USER" "$CERT_DAYS"
fi

# ---------------------------------------------------------------------------
log "4. Read the grant back by impersonation"
can() { kubectl auth can-i "$@" -n "$RUNNERS_NAMESPACE" --as "$PROJECTOR_USER" >/dev/null 2>&1; }
can update "secrets/${SECRET_NAME}" || die "${PROJECTOR_USER} cannot update secrets/${SECRET_NAME}"
can get "secrets/${SECRET_NAME}" || die "${PROJECTOR_USER} cannot get secrets/${SECRET_NAME}"
! can get "secrets/${PERSONAL_SECRET_NAME}" || die "${PROJECTOR_USER} can read secrets/${PERSONAL_SECRET_NAME}: its grant is wider than one Secret"
! can update "secrets/${PERSONAL_SECRET_NAME}" || die "${PROJECTOR_USER} can write secrets/${PERSONAL_SECRET_NAME}: its grant is wider than one Secret"
! can list secrets || die "${PROJECTOR_USER} can list secrets: its grant is wider than one Secret"
! can create secrets || die "${PROJECTOR_USER} can create secrets: its grant is wider than one Secret"

log "DONE. ${PROJECTOR_USER} may get/update/patch ${RUNNERS_NAMESPACE}/${SECRET_NAME} and no other Secret."
