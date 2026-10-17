#!/usr/bin/env bash
# FAULTS C-08: a duplicate `observe` while the run is observing (H7).
# Pass: the duplicate is refused; the run still confirms.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=0
echo "######## restore guard-vm-$I"; restore $I || exit 1
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I tmp/faults/c08.converge.log" > tmp/faults/c08.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 2; done
RUN=$(latest_run $I); echo "######## phase=$(phase_of $I) run=$RUN: duplicate observe"
guard_op $I observe "$RUN"
wait $CPID; cat tmp/faults/c08.converge.out
echo "######## after"; vm $I "sudo bash -c 'for r in /var/lib/docker-engine-guard/runs/*; do echo \$(basename \$r) \$(cat \$r/phase); done; cat /var/lib/docker-engine-guard/confirmed'"
