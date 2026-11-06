#!/usr/bin/env bash
# prove-fixture-worker.sh <host> <agent|disabled> — the fixture proof for a
# homelab worker joined by join-fixture-worker.sh, at the fixture's current
# egress-selector-mode. Run it on the worker's macOS host, from a clone of
# this repository.
#
# Governed by SPECIFICATION/non-functional-requirements.md, "Homelab worker
# nodes": "Reviewed cluster changes". Design:
# plan/homelab-k8s-worker-nodes/research/008 §4.
#
# A thin wrapper: it supplies the fixture's kubectl (run inside the fixture's
# server container), its port-forward shell and its K3s agent node as the
# peer, and runs the production proof, prove-worker.sh.
#
#   agent     the negative control (--expect-streaming-failure): with the
#             fleet's earlier egress mode the API server reaches kubelets only
#             through K3s agent tunnels, so logs and exec on the worker, which
#             runs no K3s agent, MUST fail.
#   disabled  the full proof.
set -euo pipefail

prog="prove-fixture-worker"
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hw="$here/.."
hosts_dir="${HOMELAB_WORKER_HOSTS_DIR:-$hw/hosts}"
server="k3d-hw-fixture-server-0"
peer="k3d-hw-fixture-agent-0"

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
  agent) negative=(--expect-streaming-failure) ;;
  disabled) negative=() ;;
  *) die "egress-selector-mode '$mode' is not agent or disabled" ;;
esac
worker="$host-homelab-worker"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir "$tmp/bin"
cat >"$tmp/bin/kubectl" <<EOF
#!/usr/bin/env bash
exec limactl shell --workdir / "$worker" sudo docker exec -i "$server" kubectl "\$@"
EOF
chmod 0755 "$tmp/bin/kubectl"
PATH="$tmp/bin:$PATH" \
  PORT_FORWARD_SHELL="limactl shell --workdir / $worker sudo docker exec -i $server sh -c" \
  "$hw/prove-worker.sh" "$host" --peer-node "$peer" ${negative[@]+"${negative[@]}"}
