#!/usr/bin/env bash
# FAULTS B-01 (reboot before the commit point) and B-02 (reboot after `reserve`, and
# again after `started`). Revision 7's H1 removed G8's automatic takeover, so the
# next controller is refused (I1) and the operator's recover rolls back (I2).
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=1
reboot_at() { # reboot_at <phase> <tag>
  local want=$1 tag=$2
  setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I tmp/faults/$tag.converge.log" > tmp/faults/$tag.converge.out 2>&1 &
  local cpid=$!
  until [ "$(phase_of $I)" = "$want" ] || ! kill -0 $cpid 2>/dev/null; do sleep 1; done
  RUN=$(latest_run $I); echo "######## phase=$(phase_of $I) run=$RUN at $(date -u +%T): kill the controller and reboot the guest"
  kill -KILL -- -$cpid 2>/dev/null
  vm $I 'sudo systemctl reboot' 2>/dev/null; sleep 20
  for _ in $(seq 1 60); do vm $I true 2>/dev/null && break; sleep 5; done
  echo "guest back at $(date -u +%T), boot $(vm $I 'cat /proc/sys/kernel/random/boot_id')"; sleep 30
}
after_reboot() {
  vm $I "sudo bash -c 'echo phase=\$(cat /var/lib/docker-engine-guard/runs/$RUN/phase)
    echo permission: \$(ls /run/docker-engine-guard 2>/dev/null | tr \"\n\" \" \")
    for u in containerd.service docker.service docker.socket; do echo \"\$u active=\$(systemctl is-active \$u) enabled=\$(systemctl is-enabled \$u 2>&1)\"; done
    echo docker-rules-v4: \$(iptables -S | grep -c DOCKER) v6: \$(ip6tables -S | grep -c DOCKER)
    echo docker0: \$(ip -o link show docker0 2>/dev/null | cut -d: -f2 || echo absent)
    echo forward: \$(iptables -S FORWARD | head -1)'"
}
echo "######## restore guard-vm-$I"; restore $I || exit 1
echo; echo "################ B-01 / B-02b: reboot at started"
reboot_at started b01
echo "######## after reboot (B-01 pass: no unit started, no Docker rule)"; after_reboot
echo "######## next controller converges (B-02 pass: refused, run untouched)"; converge $I tmp/faults/b02b.converge.log
after_reboot
echo "######## operator recovers the run (B-02 pass: rolled back)"; converge $I tmp/faults/b02b.recover.log -e docker_engine_recover=$RUN
rolled_back_check $I
echo; echo "################ B-02a: reboot after reserve"
reboot_at reserved b02a
echo "######## after reboot"; after_reboot
echo "######## next controller converges (refused, run untouched)"; converge $I tmp/faults/b02a.converge2.log
after_reboot
echo "######## operator recovers the run (rolled back)"; converge $I tmp/faults/b02a.recover.log -e docker_engine_recover=$RUN
rolled_back_check $I
