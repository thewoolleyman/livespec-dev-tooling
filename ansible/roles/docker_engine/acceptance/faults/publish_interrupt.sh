#!/usr/bin/env bash
# FAULTS B-06, R-06 and M-04: the guard's publish is killed while dpkg -i runs.
#   publish_interrupt.sh <vm> recover    B-06: `recover` resumes the publish; it
#                                        completes or rolls back, never stranded
#   publish_interrupt.sh <vm> rollback   R-06 + M-04: roll back from the publishing
#                                        phase; the next run is not stranded and its
#                                        publish completes the non-empty dpkg --audit
# FAULTS_KILL_ON=trigger moves the kill from the start of `dpkg -i` to the moment
# man-db's trigger handler (mandb) runs inside it, which leaves man-db
# half-configured. The guest waits and kills in one ssh call, so the controller's
# polling latency cannot miss the trigger's few seconds.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 HOW=$2 W=${FAULTS_WINDOW:-90} L=tmp/faults/pubint-$2-vm$1
echo "######## restore guard-vm-$I"; restore $I || exit 1
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
# Wait until dpkg is actually unpacking inside the publish unit, then kill both.
until vm $I 'pgrep -f "^dpkg -i" >/dev/null' 2>/dev/null || ! kill -0 $CPID 2>/dev/null; do sleep 0.3; done
RUN=$(latest_run $I)
[ -n "$RUN" ] && kill -0 $CPID 2>/dev/null || { echo "######## VOID: no guard run reached dpkg -i (see $L.converge.out); not a verdict"; exit 3; }
if [ "${FAULTS_KILL_ON:-dpkg}" = trigger ]; then
  vm $I "sudo bash -c 'for n in \$(seq 1 2400); do pgrep -x mandb >/dev/null && break; pgrep -f \"^dpkg -i\" >/dev/null || { echo no-trigger; exit 0; }; sleep 0.05; done; pgrep -x mandb >/dev/null || { echo no-trigger; exit 0; }; u=\$(systemctl list-units --plain --no-legend \"docker-engine-guard-publish-*\" | awk \"{print \\\$1}\" | head -1); echo killing \$u during the man-db trigger; systemctl kill -s KILL \$u; pkill -KILL -f \"^dpkg -i\"; pkill -KILL -x mandb; true'" | tee $L.kill.out
  grep -q no-trigger $L.kill.out && { kill -KILL -- -$CPID 2>/dev/null; echo "######## VOID: dpkg -i ended before man-db's trigger ran; not a verdict"; exit 3; }
else
vm $I "sudo bash -c 'u=\$(systemctl list-units --plain --no-legend \"docker-engine-guard-publish-*\" | awk \"{print \\\$1}\" | head -1); echo killing \$u during dpkg; systemctl kill -s KILL \$u; pkill -KILL -f \"^dpkg -i\"; true'"
fi
kill -KILL -- -$CPID 2>/dev/null
sleep 5
echo "######## run=$RUN phase=$(phase_of $I); dpkg --audit:"; vm $I 'sudo dpkg --audit | head -5'
echo "######## package states after the kill:"; vm $I "dpkg-query -W -f='\${Package} \${Status}\\n' man-db runc containerd docker.io"
if [ "$HOW" = recover ]; then
  echo "######## next controller (expect refusal)"; converge $I $L.second.log -e docker_engine_window_seconds=$W
  echo "######## recover"; converge $I $L.recover.log -e docker_engine_window_seconds=$W -e docker_engine_recover=$RUN
  vm $I "sudo bash -c 'echo phase=\$(cat /var/lib/docker-engine-guard/runs/$RUN/phase); dpkg --audit | head -3; cat /var/lib/docker-engine-guard/confirmed 2>/dev/null || echo no-marker'"
else
  echo "######## roll back from publishing"; guard_op $I rollback "$RUN"
  rolled_back_check $I
  echo "######## next run (R-06: not stranded; M-04: publish completes the audit)"; converge $I $L.next.log -e docker_engine_window_seconds=$W
  vm $I "sudo bash -c 'for r in /var/lib/docker-engine-guard/runs/*; do echo \$(basename \$r) \$(cat \$r/phase); done; echo audit: \$(dpkg --audit | wc -l) lines; cat /var/lib/docker-engine-guard/confirmed 2>/dev/null || echo no-marker'"
fi
