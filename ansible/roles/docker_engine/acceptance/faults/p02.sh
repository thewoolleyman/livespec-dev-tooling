#!/usr/bin/env bash
# FAULTS P-02: a failed sample while the observer exits. FORWARD is flipped to
# DROP <lead> seconds before the window ends, so the observer's last sample
# fails as it finishes. Pass: the rollback runs with no deadlock; rolled back.
#   p02.sh <vm> [lead-seconds]
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 LEAD=${2:-3} W=${FAULTS_WINDOW:-90} L=tmp/faults/p02-vm$1-lead$LEAD
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 0.3; done
RUN=$(latest_run $I); t0=$SECONDS; echo "######## P-02 run=$RUN observing at $(date -u +%T); flipping FORWARD at window minus ${LEAD}s"
sleep $((W - LEAD)); vm $I 'sudo iptables -P FORWARD DROP'; echo "FORWARD -> DROP at $(date -u +%T) (+$((SECONDS - t0))s)"
wait $CPID; tail -3 $L.converge.out | cut -c1-250
t1=$SECONDS; until case "$(phase_of $I)" in rolled-back|rollback-partial|confirmed) true;; *) false;; esac || [ $((SECONDS - t1)) -gt 1200 ]; do sleep 3; done
echo "######## P-02 phase=$(phase_of $I) $((SECONDS - t0))s after observing began"
vm $I "sudo journalctl -u 'docker-engine-guard-observe*' -u 'docker-engine-guard-rollback-$RUN*' --no-pager -o short-iso | grep -E 'observe (proceed|refuse)|rollback (proceed|refuse)|sample' | tail -6"
rolled_back_check $I
