#!/usr/bin/env bash
# FAULTS P-02: a failed sample while the observer exits. FORWARD is flipped to
# DROP <lead> seconds before the observer's LAST sample, so that sample fails
# as the window ends. Pass: the rollback runs with no deadlock; rolled back.
# The observer samples every 15 s plus the probes' own time, so a sample step
# measured 18.07 s on guard-vm-6 (5 samples over a 90.35 s window); a flip
# aimed at the window's end lands after the last sample and is never seen.
# The last sample therefore starts at STEP*floor((W-0.5)/STEP), about 72 s.
# A flip no sample saw is reported AIM-MISS (exit 3), never as a verdict.
#   p02.sh <vm> [lead-seconds]   FAULTS_P02_STEP overrides the measured step
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 LEAD=${2:-3} W=${FAULTS_WINDOW:-90} L=tmp/faults/p02-vm$1-lead$LEAD STEP=${FAULTS_P02_STEP:-18.07}
FLIP=$(awk -v w="$W" -v s="$STEP" -v l="$LEAD" 'BEGIN { last = s * int((w - 0.5) / s); printf "%.1f", last - l }')
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 0.3; done
RUN=$(latest_run $I); t0=$SECONDS; echo "######## P-02 run=$RUN observing at $(date -u +%T); flipping FORWARD at +${FLIP}s (${LEAD}s before the last sample)"
sleep "$FLIP"; vm $I 'sudo iptables -P FORWARD DROP'; echo "FORWARD -> DROP at $(date -u +%T) (+$((SECONDS - t0))s)"
wait $CPID; tail -3 $L.converge.out | cut -c1-250
if vm $I "sudo journalctl -u docker-engine-guard-observe.service --since=-$((SECONDS - t0 + 60))s --no-pager -o cat | grep -q 'observe proceed'"; then
  echo "######## P-02 AIM-MISS: the observer passed every sample, so the flip landed after its last sample; not a verdict"; exit 3; fi
t1=$SECONDS; until case "$(phase_of $I)" in rolled-back|rollback-partial|confirmed) true;; *) false;; esac || [ $((SECONDS - t1)) -gt 1200 ]; do sleep 3; done
echo "######## P-02 phase=$(phase_of $I) $((SECONDS - t0))s after observing began"
vm $I "sudo journalctl -u 'docker-engine-guard-observe*' -u 'docker-engine-guard-rollback-$RUN*' --no-pager -o short-iso | grep -E 'observe (proceed|refuse)|rollback (proceed|refuse)|sample' | tail -6"
rolled_back_check $I
