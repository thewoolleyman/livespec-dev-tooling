#!/usr/bin/env bash
# FAULTS H-02: a second converge on the confirmed host, then a third (H7).
# Pass: no reservation, no change, both runs.
set -uo pipefail
cd "$(dirname "$0")/../../../../.." || exit 1
KEY=$HOME/.cache/docker-engine-guard-acceptance/poweredge-xubuntu/id_ed25519
vm0() { ssh -i "$KEY" -o ProxyJump=cwoolley@poweredge-xubuntu -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o BatchMode=yes -o LogLevel=ERROR -p 2229 guard@127.0.0.1 "$@"; }
state() {
  vm0 'sudo bash -c "
    echo runs: \$(ls /var/lib/docker-engine-guard/runs | sort | tr \"\n\" \" \")
    for f in /var/lib/docker-engine-guard/*; do [ -f \"\$f\" ] && echo \"\$(basename \$f): \$(sha256sum < \$f | cut -c1-16)\"; done
    for r in /var/lib/docker-engine-guard/runs/*; do echo \"\$(basename \$r) phase=\$(cat \$r/phase)\"; done
    for u in containerd.service docker.service docker.socket; do echo \"\$u \$(systemctl is-enabled \$u)/\$(systemctl is-active \$u) since=\$(systemctl show -p ActiveEnterTimestampMonotonic --value \$u)\"; done
    echo daemon.json: \$(sha256sum < /etc/docker/daemon.json | cut -c1-16)
    echo forward: \$(iptables -S FORWARD | head -1) / \$(ip6tables -S FORWARD | head -1)
  "'
}
echo "######## before"; state | tee tmp/faults/h02.before
for n in 2 3; do
  echo "######## converge $n"
  mise exec -- just ansible-apply -i ansible/roles/docker_engine/acceptance/inventory-kvm.yml ansible/docker-engine.yml --limit guard-vm-0 > tmp/faults/h02.converge$n.log 2>&1
  echo "exit=$?"
  grep -A1 "PLAY RECAP" tmp/faults/h02.converge$n.log | tail -1
  grep -E "^(TASK|changed:)" tmp/faults/h02.converge$n.log | grep -B1 "^changed:" | grep "^TASK" | sed 's/^/changed-task: /'
  grep -iE "reserv" tmp/faults/h02.converge$n.log | grep -E "^TASK" | sed 's/^/reserve-task-seen: /'
  echo "######## after converge $n"; state | tee tmp/faults/h02.after$n
  diff tmp/faults/h02.before tmp/faults/h02.after$n > /dev/null && echo "STATE UNCHANGED" || { echo "STATE CHANGED:"; diff tmp/faults/h02.before tmp/faults/h02.after$n; }
done
