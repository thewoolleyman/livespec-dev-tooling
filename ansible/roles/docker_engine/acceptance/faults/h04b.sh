#!/usr/bin/env bash
# FAULTS H-04, redone: a reconfigure to a configuration NEITHER the marker nor the
# reconfigured record covers, killed after its daemon.json write. Pass: the next
# converge's reconfigure completes it (the reconfigured record covers the new keys).
set -uo pipefail
cd "$(dirname "$0")/../../../../.." || exit 1
# WHICH MACHINE HOSTS THE VMs IS THE INVENTORY'S DECISION, NEVER THIS FILE'S
# (livespec-dev-tooling-prdxxe). Told in one variable that ../inventory-kvm.yml and
# lib.sh read from the same environment; refused before anything is touched.
KVM_HOST="${DOCKER_ENGINE_ACCEPTANCE_KVM_HOST:?set this to the inventory name of the KVM acceptance host (the docker_engine_acceptance_hosts group member) before running a FAULTS case}"
# The login account on that host. A user is not a machine, so it stays a literal.
KVM_USER="${DOCKER_ENGINE_ACCEPTANCE_KVM_USER:-cwoolley}"
KEY=$HOME/.cache/docker-engine-guard-acceptance/$KVM_HOST/id_ed25519
vm0() { ssh -i "$KEY" -o ProxyJump="$KVM_USER@$KVM_HOST" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o LogLevel=ERROR -p 2229 guard@127.0.0.1 "$@"; }
state() {
  vm0 'sudo python3 - <<PY
import json, hashlib, glob
root = "/var/lib/docker-engine-guard"
marker = json.load(open(root + "/confirmed"))
rec = json.load(open(root + "/reconfigured")) if __import__("os").path.exists(root + "/reconfigured") else {}
run = marker["run"]
inputs = json.load(open(f"{root}/runs/{run}/inputs/daemon.json"))
d = lambda k: hashlib.sha256(json.dumps(k, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]
host = json.load(open("/etc/docker/daemon.json"))
print("marker digest      ", marker.get("digest", "")[:16])
print("reconfigured digest", rec.get("digest", "")[:16] or "ABSENT")
print("inputs digest      ", d(inputs))
print("daemon.json live-restore=%s ipv6=%s ip-forward-no-drop=%s" % (host.get("live-restore"), host.get("ipv6"), host.get("ip-forward-no-drop")))
import os; print("restart-pending:", open("/var/lib/docker-sandbox-slice/restart-pending").read().strip() if os.path.exists("/var/lib/docker-sandbox-slice/restart-pending") else "ABSENT")
PY'
}
base='"iptables":true,"ip6tables":true,"ip-forward":true,"ipv6":false,"bip":"172.17.0.1/16","cgroup-parent":"fabro-sandbox.slice"'
base2=${base/\"ipv6\":false/\"ipv6\":true}
CFG1="{\"docker_engine_daemon_config\":{$base,\"ip-forward-no-drop\":true,\"live-restore\":true}}"
CFG2="{\"docker_engine_daemon_config\":{$base2,\"ip-forward-no-drop\":true,\"live-restore\":true}}"
converge() {
  mise exec -- just ansible-apply -i ansible/roles/docker_engine/acceptance/inventory-kvm.yml ansible/docker-engine.yml --limit guard-vm-0 -e "$1" > "$2" 2>&1
  echo "exit=$?"; grep -A1 "PLAY RECAP" "$2" | tail -1
  grep -c "TASK \[docker_engine : Run guard operation reconfigure\]" "$2" | sed 's/^/reconfigure ran: /'
}
echo "######## reset: converge to CFG1 (live-restore=true, ip-forward-no-drop=true)"; converge "$CFG1" tmp/faults/h04b.reset.log; state
echo "######## inject: CFG2 uploaded and written to daemon.json, then the guard dies"
vm0 'sudo python3 - <<PY
import json, sys
root = "/var/lib/docker-engine-guard"
run = json.load(open(root + "/confirmed"))["run"]
keys = {"iptables": True, "ip6tables": True, "ip-forward": True, "ipv6": True, "bip": "172.17.0.1/16",
        "cgroup-parent": "fabro-sandbox.slice", "ip-forward-no-drop": True, "live-restore": True}
open(f"{root}/runs/{run}/inputs/daemon.json", "w").write(json.dumps(keys, indent=2) + "\n")
sys.path.insert(0, "/usr/local/lib/docker-engine-guard")
from livespec_dev_tooling.fleet._docker_engine_guard_daemon import write_daemon_keys
write_daemon_keys(keys=keys)
print("injected")
PY'
state
echo "######## converge with CFG2 (the same keys the interrupted reconfigure was writing)"; converge "$CFG2" tmp/faults/h04b.converge.log; state
echo "######## the guard's own view: confirm on the committed run"
vm0 'R=$(sudo python3 -c "import json;print(json.load(open(\"/var/lib/docker-engine-guard/confirmed\"))[\"run\"])"); U=docker-engine-guard-confirm-$R-h04b-$(date +%H%M%S); S=$(date +%s); sudo systemd-run --unit=$U --wait --collect --quiet --property=Type=oneshot --property=TimeoutStartSec=420 /usr/local/libexec/docker-engine-guard confirm $R --window-seconds=420; echo "confirm exit=$?"; sudo journalctl -u $U.service --since=@$S --no-pager -o cat | grep -iE "confirm (finish|proceed|refuse)"'
