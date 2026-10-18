#!/usr/bin/env bash
# FAULTS C-09 (H7): the observer paused, then a rollback, then the observer
# resumed. Pass: the observer is dead; rolled back. The implemented observer has
# no separate canary-creation step (the canary is resolved inside every sample),
# so the pause lands at the first instant the run reads `observing`, which is
# the earliest point the design's "just before canary creation" can name.
#   c09.sh <vm>
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 W=${FAULTS_WINDOW:-90} L=tmp/faults/c09-vm$1
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
until [ -n "$(latest_run $I)" ] || ! kill -0 $CPID 2>/dev/null; do sleep 0.5; done
RUN=$(latest_run $I)
vm $I "sudo tee /run/guest_inject.sh >/dev/null" < ansible/roles/docker_engine/acceptance/faults/guest_inject.sh
vm $I "sudo systemd-run --unit=fault-inject-$RUN --collect bash /run/guest_inject.sh pause-observer - $RUN"
echo "######## c09 run=$RUN injector armed at $(date -u +%T)"
t0=$SECONDS; until case "$(phase_of $I)" in rolled-back|rollback-partial|confirmed) true;; *) false;; esac || [ $((SECONDS-t0)) -gt 1500 ]; do sleep 3; done
sleep 8; kill -TERM -- -$CPID 2>/dev/null; sleep 2; kill -KILL -- -$CPID 2>/dev/null
echo "######## c09 phase=$(phase_of $I)"
echo "-- injector:"; vm $I "sudo cat /run/fault-inject-$RUN.log"
rolled_back_check $I
