#!/usr/bin/env bash
# prove-fixture-worker.sh <host> <agent|disabled> — the fixture proof for a
# homelab worker joined by join-fixture-worker.sh, at the fixture's current
# egress-selector-mode. Run it on the worker's macOS host, from a clone of
# this repository. It prints one `PROOF <check> PASS|FAIL <detail>` line per
# check and exits non-zero when any check fails.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Reviewed cluster changes". Design:
# plan/homelab-k8s-worker-nodes/research/006 §3.
#
#   agent     the negative control: with the fleet's current egress mode the
#             API server reaches kubelets only through K3s agent tunnels, so
#             logs and exec on the worker, which runs no K3s agent, MUST fail.
#   disabled  the change under proof: logs, exec, port-forward and kubelet
#             stats on the worker MUST work, logs on the K3s node MUST still
#             work, and so must pod-to-pod traffic both ways between the
#             worker and a K3s node, a ClusterIP Service and cluster DNS
#             (10.43.0.10) from the worker, a NetworkPolicy deny enforced on
#             a worker pod (allowed, denied, allowed again), and 4 MiB TCP
#             transfers both ways plus a 1400-byte ping across the worker's
#             smaller tailnet MTU.
#
# Proof pods tolerate the worker's admission hold and live in namespace
# hw-proof, which is deleted at the end unless KEEP=1.
set -euo pipefail

prog="prove-fixture-worker"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hw="$here/.."
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
server="k3d-hw-fixture-server-0"
k3s_node="k3d-hw-fixture-agent-0"
ns="hw-proof"
busybox="docker.io/library/busybox:1.37.0@sha256:a7dbc319b1438115a207e11930dc4bb3e643dcb3ec0bdd694bb36cd8fad289ec"

die() {
  printf '%s: %s\n' "$prog" "$*" >&2
  exit 1
}

[ "$#" -eq 2 ] || die "usage: $prog <host> <agent|disabled>"
host="$1"
mode="$2"
case "$host" in
  *[!a-z0-9-]* | -*) die "host '$host' is not a valid host name" ;;
esac
[ -f "$hosts_dir/$host.env" ] || die "host '$host' is not declared in homelab-worker/hosts/"
case "$mode" in
  agent | disabled) ;;
  *) die "egress-selector-mode '$mode' is not agent or disabled" ;;
esac
worker="$host-homelab-worker"

tmp="$(mktemp -d)"
cleanup() {
  if [ "${KEEP:-0}" != "1" ]; then
    kubectl delete namespace "$ns" --wait=false >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT
mkdir "$tmp/bin"
cat >"$tmp/bin/kubectl" <<EOF
#!/usr/bin/env bash
exec limactl shell --workdir / "$worker" sudo docker exec -i "$server" kubectl "\$@"
EOF
chmod 0755 "$tmp/bin/kubectl"
PATH="$tmp/bin:$PATH"
export PATH

# in_server <command...>: run a command inside the fixture's server container.
in_server() {
  limactl shell --workdir / "$worker" sudo docker exec -i "$server" "$@"
}

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
  pod server-k3s "$k3s_node" server-k3s "$server_cmd"
  pod client-worker "$worker" client "$client_cmd"
  pod client-k3s "$k3s_node" client "$client_cmd"
  for app in server-worker server-k3s; do
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

if [ "$mode" = "agent" ]; then
  expect logs-on-worker fail kubectl logs --namespace "$ns" client-worker
  expect exec-on-worker fail kubectl exec --namespace "$ns" client-worker -- echo exec-ok
else
  expect logs-on-worker ok kubectl logs --namespace "$ns" client-worker
  expect exec-on-worker ok kubectl exec --namespace "$ns" client-worker -- echo exec-ok
  expect logs-on-k3s-node ok kubectl logs --namespace "$ns" client-k3s
  expect kubelet-stats-on-worker ok kubectl get --raw "/api/v1/nodes/$worker/proxy/stats/summary"
  expect port-forward-to-worker ok in_server sh -c "kubectl port-forward --namespace $ns pod/server-worker 18080:8080 >/dev/null 2>&1 & pf=\$!; sleep 3; (wget -qO- -T 5 http://127.0.0.1:18080/ || curl -fsS -m 5 http://127.0.0.1:18080/); rc=\$?; kill \$pf; exit \$rc"
  ip_worker="$(kubectl get pod --namespace "$ns" server-worker -o 'jsonpath={.status.podIP}')"
  ip_k3s="$(kubectl get pod --namespace "$ns" server-k3s -o 'jsonpath={.status.podIP}')"
  expect pod-to-pod-worker-to-k3s ok kubectl exec --namespace "$ns" client-worker -- wget -qO- -T 5 "http://$ip_k3s:8080/"
  expect pod-to-pod-k3s-to-worker ok kubectl exec --namespace "$ns" client-k3s -- wget -qO- -T 5 "http://$ip_worker:8080/"
  # MTU asymmetry (research 007): over the tailnet underlay the worker's
  # flannel MTU is 1230 against the nodes' 1450.
  expect large-tcp-worker-to-k3s ok kubectl exec --namespace "$ns" client-worker -- wget -qO /dev/null -T 30 "http://$ip_k3s:8080/big"
  expect large-tcp-k3s-to-worker ok kubectl exec --namespace "$ns" client-k3s -- wget -qO /dev/null -T 30 "http://$ip_worker:8080/big"
  expect large-icmp-worker-to-k3s ok kubectl exec --namespace "$ns" client-worker -- ping -c 3 -W 5 -s 1400 "$ip_k3s"
  expect clusterip-and-dns-from-worker ok kubectl exec --namespace "$ns" client-worker -- wget -qO- -T 5 "http://server-k3s.$ns.svc.cluster.local:8080/"
  expect dns-10.43.0.10-from-worker ok kubectl exec --namespace "$ns" client-worker -- nslookup kubernetes.default.svc.cluster.local 10.43.0.10
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
  expect networkpolicy-deny-on-worker fail kubectl exec --namespace "$ns" client-k3s -- wget -qO- -T 5 "http://$ip_worker:8080/"
  kubectl delete networkpolicy --namespace "$ns" deny-to-server-worker >/dev/null
  sleep "${POLICY_SETTLE_SECONDS:-10}"
  expect networkpolicy-lifted-on-worker ok kubectl exec --namespace "$ns" client-k3s -- wget -qO- -T 5 "http://$ip_worker:8080/"
fi

[ "$failed" -eq 0 ] || die "the fixture proof at egress-selector-mode $mode FAILED"
printf '%s: the fixture proof at egress-selector-mode %s PASSED\n' "$prog" "$mode"
