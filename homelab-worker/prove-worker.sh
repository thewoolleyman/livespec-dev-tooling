#!/usr/bin/env bash
# prove-worker.sh <host> --peer-node <node> [--expect-streaming-failure]
# — prove a homelab worker joined to the cluster the caller's `kubectl`
# reaches. It prints one `PROOF <check> PASS|FAIL <detail>` line per check and
# exits non-zero when any check fails.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes". Design: plan/homelab-k8s-worker-nodes/research/008 §4.
#
# By default it proves the joined worker: logs, exec, port-forward and kubelet
# stats on the worker, logs on --peer-node (an existing node, the regression
# check), pod-to-pod both ways between the worker and --peer-node, 4 MiB TCP
# transfers both ways plus a 1400-byte ping, a ClusterIP Service and cluster
# DNS from the worker, and a NetworkPolicy deny enforced on a worker pod
# (allowed, denied, allowed again).
#
# With --expect-streaming-failure it runs the negative control instead: logs
# and exec on the worker MUST fail, as they do while the API server reaches
# kubelets only through K3s agent tunnels.
#
# PORT_FORWARD_SHELL (default `bash -c`) runs the port-forward check, so a
# caller whose kubectl runs elsewhere can run the check where kubectl runs.
# Proof pods tolerate the worker's admission hold and live in namespace
# hw-proof, which is deleted at the end unless KEEP=1.
set -euo pipefail

prog="prove-worker"
hw="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
ns="hw-proof"
busybox="docker.io/library/busybox:1.37.0@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

usage="usage: $prog <host> --peer-node <node> [--expect-streaming-failure]"
[ "$#" -ge 1 ] || die "$usage"
host="$1"
shift
peer=""
negative=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --peer-node)
      [ "$#" -ge 2 ] || die "--peer-node needs a value; $usage"
      peer="$2"
      shift 2
      ;;
    --expect-streaming-failure)
      negative=1
      shift
      ;;
    *) die "unknown argument '$1'; $usage" ;;
  esac
done
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
[ -n "$peer" ] || die "--peer-node is required; $usage"
worker="$host-homelab-worker"
read -r -a pf_shell <<<"${PORT_FORWARD_SHELL:-bash -c}"

cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then
    kubectl delete namespace "$ns" --wait=false >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

failed=0
result() {
  printf 'PROOF %s %s %s\n' "$1" "$2" "$3"
  [ "$2" = "PASS" ] || failed=1
}

# pod <name> <node> <app> <shell command>
pod() {
  cat <<EOF
---
apiVersion: v1
kind: Pod
metadata:
  name: $1
  namespace: $ns
  labels:
    app: $3
spec:
  nodeName: $2
  tolerations:
    - key: homelab-worker.livespec.dev/admission
      operator: Exists
      effect: NoSchedule
  containers:
    - name: main
      image: $busybox
      command: [sh, -c, "$4"]
EOF
}

server_cmd="mkdir -p /www && echo proof-ok > /www/index.html && dd if=/dev/zero of=/www/big bs=1024 count=4096 2>/dev/null && exec httpd -f -p 8080 -h /www"
client_cmd="echo proof-ready && exec sleep 3600"
{
  printf 'apiVersion: v1\nkind: Namespace\nmetadata:\n  name: %s\n' "$ns"
  pod server-worker "$worker" server-worker "$server_cmd"
  pod server-peer "$peer" server-peer "$server_cmd"
  pod client-worker "$worker" client "$client_cmd"
  pod client-peer "$peer" client "$client_cmd"
  for app in server-worker server-peer; do
    printf -- '---\napiVersion: v1\nkind: Service\nmetadata:\n  name: %s\n  namespace: %s\nspec:\n  selector:\n    app: %s\n  ports:\n    - port: 8080\n' "$app" "$ns" "$app"
  done
} | kubectl apply -f - >/dev/null
kubectl wait --namespace "$ns" --for=condition=Ready pod --all --timeout=300s >/dev/null ||
  die "the proof pods did not become Ready"

# expect <check> <want: ok|fail> <command...>
expect() {
  local check="$1" want="$2" out got
  shift 2
  if out="$("$@" 2>&1)"; then got="ok"; else got="fail"; fi
  out="$(printf '%s' "$out" | tr '\n' ' ' | cut -c1-160)"
  if [ "$got" = "$want" ]; then
    result "$check" PASS "expected $want: $out"
  else
    result "$check" FAIL "expected $want, got $got: $out"
  fi
}

if [ "$negative" = 1 ]; then
  expect logs-on-worker fail kubectl logs --namespace "$ns" client-worker
  expect exec-on-worker fail kubectl exec --namespace "$ns" client-worker -- echo exec-ok
else
  expect logs-on-worker ok kubectl logs --namespace "$ns" client-worker
  expect exec-on-worker ok kubectl exec --namespace "$ns" client-worker -- echo exec-ok
  expect logs-on-peer-node ok kubectl logs --namespace "$ns" client-peer
  expect kubelet-stats-on-worker ok kubectl get --raw "/api/v1/nodes/$worker/proxy/stats/summary"
  expect port-forward-to-worker ok "${pf_shell[@]}" "kubectl port-forward --namespace $ns pod/server-worker 18080:8080 >/dev/null 2>&1 & pf=\$!; sleep 3; (wget -qO- -T 5 http://127.0.0.1:18080/ || curl -fsS -m 5 http://127.0.0.1:18080/); rc=\$?; kill \$pf; exit \$rc"
  ip_worker="$(kubectl get pod --namespace "$ns" server-worker -o 'jsonpath={.status.podIP}')"
  ip_peer="$(kubectl get pod --namespace "$ns" server-peer -o 'jsonpath={.status.podIP}')"
  cluster_dns="$(kubectl get service --namespace kube-system kube-dns -o 'jsonpath={.spec.clusterIP}')"
  expect pod-to-pod-worker-to-peer ok kubectl exec --namespace "$ns" client-worker -- wget -qO- -T 5 "http://$ip_peer:8080/"
  expect pod-to-pod-peer-to-worker ok kubectl exec --namespace "$ns" client-peer -- wget -qO- -T 5 "http://$ip_worker:8080/"
  expect large-tcp-worker-to-peer ok kubectl exec --namespace "$ns" client-worker -- wget -qO /dev/null -T 30 "http://$ip_peer:8080/big"
  expect large-tcp-peer-to-worker ok kubectl exec --namespace "$ns" client-peer -- wget -qO /dev/null -T 30 "http://$ip_worker:8080/big"
  expect large-icmp-worker-to-peer ok kubectl exec --namespace "$ns" client-worker -- ping -c 3 -W 5 -s 1400 "$ip_peer"
  expect clusterip-and-dns-from-worker ok kubectl exec --namespace "$ns" client-worker -- wget -qO- -T 5 "http://server-peer.$ns.svc.cluster.local:8080/"
  expect cluster-dns-from-worker ok kubectl exec --namespace "$ns" client-worker -- nslookup kubernetes.default.svc.cluster.local "$cluster_dns"
  kubectl apply -f - >/dev/null <<EOF
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-to-server-worker
  namespace: $ns
spec:
  podSelector:
    matchLabels:
      app: server-worker
  policyTypes: [Ingress]
EOF
  sleep "${POLICY_SETTLE_SECONDS:-10}"
  expect networkpolicy-deny-on-worker fail kubectl exec --namespace "$ns" client-peer -- wget -qO- -T 5 "http://$ip_worker:8080/"
  kubectl delete networkpolicy --namespace "$ns" deny-to-server-worker >/dev/null
  sleep "${POLICY_SETTLE_SECONDS:-10}"
  expect networkpolicy-lifted-on-worker ok kubectl exec --namespace "$ns" client-peer -- wget -qO- -T 5 "http://$ip_worker:8080/"
fi

if [ "$negative" = 1 ]; then label="the streaming negative control"; else label="the worker proof"; fi
[ "$failed" -eq 0 ] || die "$label FAILED"
printf '%s: %s PASSED\n' "$prog" "$label"
