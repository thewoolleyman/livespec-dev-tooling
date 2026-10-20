#!/usr/bin/env bash
# FAULTS H-03 (post-commit reconfigure with a changed owned key) and
# H-04 (reconfigure interrupted mid-write; the next reconfigure completes it).
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
  vm0 'sudo bash -c "
    cd /var/lib/docker-engine-guard
    for f in *; do [ -f \"\$f\" ] && echo \"\$f: \$(sha256sum < \$f | cut -c1-16)\"; done
    echo reconfigured: \$(cat reconfigured 2>/dev/null || echo ABSENT)
    echo restart-pending: \$(cat /var/lib/docker-sandbox-slice/restart-pending 2>/dev/null || echo ABSENT)
    echo live-restore in daemon.json: \$(python3 -c \"import json;print(json.load(open(\\\"/etc/docker/daemon.json\\\")).get(\\\"live-restore\\\"))\")
    echo docker.service since=\$(systemctl show -p ActiveEnterTimestampMonotonic --value docker.service) containerd since=\$(systemctl show -p ActiveEnterTimestampMonotonic --value containerd.service)
  "'
}
CFG_TRUE='{"docker_engine_daemon_config":{"iptables":true,"ip6tables":true,"ip-forward":true,"ip-forward-no-drop":true,"ipv6":false,"bip":"172.17.0.1/16","cgroup-parent":"fabro-sandbox.slice","live-restore":true}}'
CFG_FALSE='{"docker_engine_daemon_config":{"iptables":true,"ip6tables":true,"ip-forward":true,"ip-forward-no-drop":true,"ipv6":false,"bip":"172.17.0.1/16","cgroup-parent":"fabro-sandbox.slice","live-restore":false}}'
converge() {
  mise exec -- just ansible-apply -i ansible/roles/docker_engine/acceptance/inventory-kvm.yml ansible/docker-engine.yml --limit guard-vm-0 -e "$1" > "$2" 2>&1
  echo "exit=$?"; grep -A1 "PLAY RECAP" "$2" | tail -1
  grep -E "^TASK" "$2" | grep -iE "reconfigure|drained" | sed 's/^/task: /'
}

echo "######## H-03 before"; state
echo "######## H-03 converge with live-restore=true"; converge "$CFG_TRUE" tmp/faults/h03.converge.log
echo "######## H-03 after"; state

echo; echo "######## H-04 inject: a reconfigure killed after the daemon.json write"
vm0 'sudo bash -s' <<'GUEST'
set -eu
RUN=$(python3 -c 'import json;print(json.load(open("/var/lib/docker-engine-guard/confirmed"))["run"])' 2>/dev/null || ls /var/lib/docker-engine-guard/runs | head -1)
echo "committed run: $RUN"
rm -f /var/lib/docker-sandbox-slice/restart-pending
python3 - "$RUN" <<'PY'
import json, sys
run = sys.argv[1]
keys = {"iptables": True, "ip6tables": True, "ip-forward": True, "ip-forward-no-drop": True, "ipv6": False,
        "bip": "172.17.0.1/16", "cgroup-parent": "fabro-sandbox.slice", "live-restore": False}
# Step 1 of the role: upload the owned keys into the committed run's inputs.
open(f"/var/lib/docker-engine-guard/runs/{run}/inputs/daemon.json", "w").write(json.dumps(keys, indent=2) + "\n")
# Step 1 of the guard's reconfigure: the durable merge into daemon.json. Then the process dies.
sys.path.insert(0, "/usr/local/lib/docker-engine-guard")
from livespec_dev_tooling.fleet._docker_engine_guard_daemon import write_daemon_keys
write_daemon_keys(keys=keys)
print("injected: inputs and daemon.json carry live-restore=false; no digest record, no restart marker")
PY
GUEST
echo "######## H-04 after injection"; state
echo "######## H-04 converge with live-restore=false (the same keys)"; converge "$CFG_FALSE" tmp/faults/h04.converge.log
echo "######## H-04 after"; state
