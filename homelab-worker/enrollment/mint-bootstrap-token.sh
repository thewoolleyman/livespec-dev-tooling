#!/usr/bin/env bash
# mint-bootstrap-token.sh <host> <api-server-url> <ca-file> <out-dir> — the
# operator's controller-side step that lets one homelab worker bootstrap.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Standard bootstrap under an admission hold" (a short-lived, narrowly
# scoped bootstrap credential; enrollment material never in an image layer, in
# Git, in a command argument or in a logged or inspect-visible environment
# variable). Design: plan/homelab-k8s-worker-nodes/research/005 §3.
#
# It creates one kube-system bootstrap-token Secret that authenticates only in
# the group system:bootstrappers:homelab-worker (bound by rbac.yaml) and
# expires after TOKEN_TTL_MINUTES (default 60); the token cleaner deletes it
# then. It creates <out-dir> (mode 0700) holding the worker's enrollment:
# bootstrap-kubeconfig (mode 0600), pinning the API server URL and its CA, and
# client-ca.crt, the cluster's client CA, which the worker's kubelet needs to
# authenticate the API server's logs and exec calls. The token secret reaches
# kubectl on stdin and the kubeconfig on disk, and is printed nowhere.
#
# Run it with an admin kubeconfig for the target cluster (KUBECONFIG), from the
# operator's machine. The start task never runs it: a worker cannot mint its
# own credential.
set -euo pipefail

prog="mint-bootstrap-token"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$here/../hosts}"
ttl_minutes="${TOKEN_TTL_MINUTES:-60}"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

declared_hosts() {
  local f
  for f in "$hosts_dir"/*.env; do
    [ -e "$f" ] || continue
    f="${f##*/}"
    printf '%s ' "${f%.env}"
  done
}

[ "$#" -eq 4 ] || die "usage: $prog <host> <api-server-url> <ca-file> <out-dir>; declared hosts: $(declared_hosts)"
host="$1"
server="$2"
ca_file="$3"
out="$4"
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name; declared hosts: $(declared_hosts)" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/; declared hosts: $(declared_hosts)"
case "$server" in
  https://*) ;;
  *) die "api-server-url '$server' is not an https:// URL" ;;
esac
[ -s "$ca_file" ] || die "CA file '$ca_file' is missing or empty"
case "$ttl_minutes" in
  '' | *[!0-9]*) die "TOKEN_TTL_MINUTES '$ttl_minutes' is not a whole number of minutes" ;;
esac
[ "$ttl_minutes" -ge 5 ] && [ "$ttl_minutes" -le 1440 ] || die "TOKEN_TTL_MINUTES must be between 5 and 1440"
[ ! -e "$out" ] || die "$out already exists; refusing to overwrite an enrollment"

worker="$host-homelab-worker"

# rand <n>: n characters of [a-z0-9], the bootstrap-token alphabet. A fixed
# read from /dev/urandom, so no stage of the pipe is cut off by SIGPIPE (which
# pipefail would turn into a failure).
rand() {
  head -c 4096 /dev/urandom | LC_ALL=C tr -dc 'a-z0-9' | cut -c "1-$1"
}
token_id="$(rand 6)"
token_secret="$(rand 16)"
[ "${#token_id}" -eq 6 ] && [ "${#token_secret}" -eq 16 ] || die "could not draw a random bootstrap token"

now="$(date -u +%s)"
expires_epoch=$((now + ttl_minutes * 60))
if expiration="$(date -u -d "@$expires_epoch" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null)"; then
  :
else
  expiration="$(date -u -r "$expires_epoch" +%Y-%m-%dT%H:%M:%SZ)"
fi

client_ca="$(kubectl get configmap --namespace kube-system extension-apiserver-authentication -o 'jsonpath={.data.client-ca-file}')"
case "$client_ca" in
  "-----BEGIN CERTIFICATE-----"*) ;;
  *) die "could not read the cluster client CA from kube-system/extension-apiserver-authentication" ;;
esac

kubectl apply -f - >/dev/null <<EOF
apiVersion: v1
kind: Secret
metadata:
  name: bootstrap-token-$token_id
  namespace: kube-system
  labels:
    homelab-worker.livespec.dev/enrollment: "true"
    homelab-worker.livespec.dev/worker: "$worker"
type: bootstrap.kubernetes.io/token
stringData:
  description: "homelab worker bootstrap for $worker"
  token-id: "$token_id"
  token-secret: "$token_secret"
  expiration: "$expiration"
  usage-bootstrap-authentication: "true"
  auth-extra-groups: "system:bootstrappers:homelab-worker"
EOF

ca_data="$(base64 <"$ca_file" | tr -d '\n')"
umask 077
mkdir -p "$out"
chmod 0700 "$out"
printf '%s\n' "$client_ca" >"$out/client-ca.crt"
cat >"$out/bootstrap-kubeconfig" <<EOF
apiVersion: v1
kind: Config
clusters:
  - name: fleet
    cluster:
      server: $server
      certificate-authority-data: $ca_data
users:
  - name: $worker-bootstrap
    user:
      token: $token_id.$token_secret
contexts:
  - name: bootstrap
    context:
      cluster: fleet
      user: $worker-bootstrap
current-context: bootstrap
EOF
chmod 0600 "$out/bootstrap-kubeconfig"

printf '%s: minted bootstrap token %s for %s, expiring %s; enrollment at %s\n' \
  "$prog" "$token_id" "$worker" "$expiration" "$out"
