#!/usr/bin/env bash
# render-sa-kubeconfig.sh — render a static kubeconfig for a ServiceAccount
# from its populated long-lived token Secret, for a HOST-side process that
# needs a scoped cluster credential (today: the Kueue-webhook probe,
# ../../observability/ci-kueue-webhook-probe.sh).
#
# WHY THIS EXISTS: a kubeconfig built from a ServiceAccount token is only as
# durable as the ServiceAccount. The datastore is tmpfs and EMPTY on every
# boot (../datastore-tmpfs/), so after the 2026-09-02 reboot the probe's
# credential — hand-rendered once on 2026-08-28 — pointed at an account that
# no longer existed and the probe failed every five minutes (`Unauthorized`).
# The reconstruct-on-boot converge now re-applies the RBAC manifest and calls
# THIS script to re-render the file, so the credential is rebuilt from git on
# every boot with no hand step. The token is written to the destination only:
# never echoed, never left in a temp file.
#
# Usage:
#   render-sa-kubeconfig.sh --namespace NS --secret SECRET --user NAME \
#                           --dest PATH [--group GROUP] [--mode MODE]
# The Secret must be `type: kubernetes.io/service-account-token` annotated
# with the ServiceAccount; the token controller populates it asynchronously,
# so this waits up to 60 s for `data.token` to appear.
set -euo pipefail

namespace=""; secret=""; user=""; dest=""; group="root"; mode="0600"
while [ $# -gt 0 ]; do
  case "$1" in
    --namespace) namespace="$2"; shift 2 ;;
    --secret) secret="$2"; shift 2 ;;
    --user) user="$2"; shift 2 ;;
    --dest) dest="$2"; shift 2 ;;
    --group) group="$2"; shift 2 ;;
    --mode) mode="$2"; shift 2 ;;
    *) echo "FATAL: unknown argument $1" >&2; exit 2 ;;
  esac
done
for v in namespace secret user dest; do
  [ -n "${!v}" ] || { echo "FATAL: --${v} is required" >&2; exit 2; }
done
command -v kubectl >/dev/null || { echo "FATAL: kubectl not found on PATH" >&2; exit 1; }
: "${KUBECONFIG:?set KUBECONFIG to the ADMIN kubeconfig used to read the token Secret}"

token=""
for _ in $(seq 1 30); do
  token="$(kubectl -n "$namespace" get secret "$secret" -o jsonpath='{.data.token}' 2>/dev/null | base64 -d || true)"
  [ -n "$token" ] && break
  sleep 2
done
[ -n "$token" ] || { echo "FATAL: ${namespace}/${secret} token never populated" >&2; exit 1; }
ca_b64="$(kubectl -n "$namespace" get secret "$secret" -o jsonpath='{.data.ca\.crt}')"
[ -n "$ca_b64" ] || { echo "FATAL: ${namespace}/${secret} carries no ca.crt" >&2; exit 1; }

install -d -m 0755 "$(dirname "$dest")"
umask 077
tmp="$(mktemp "$(dirname "$dest")/.render-sa-kubeconfig.XXXXXX")"
cat > "$tmp" <<KC
apiVersion: v1
kind: Config
clusters:
- name: k3s
  cluster:
    server: https://127.0.0.1:6443
    certificate-authority-data: ${ca_b64}
contexts:
- name: ${user}@k3s
  context:
    cluster: k3s
    user: ${user}
current-context: ${user}@k3s
users:
- name: ${user}
  user:
    token: ${token}
KC
unset token
chown "root:${group}" "$tmp"
chmod "$mode" "$tmp"
mv -f "$tmp" "$dest"
echo "rendered ${dest} for ${namespace}/${user} (root:${group} ${mode})"
