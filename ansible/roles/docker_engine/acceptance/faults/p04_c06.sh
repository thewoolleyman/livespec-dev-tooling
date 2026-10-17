#!/usr/bin/env bash
# FAULTS P-04: the controller's confirmation is withheld (the controller is killed
# while the run is observing). Pass: the deadline restores FORWARD and removes
# Docker's chains; SSH answers. Then C-06: `confirm` after the deadline is refused.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=3
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I tmp/faults/p04.converge.log" > tmp/faults/p04.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 2; done
echo "######## phase=$(phase_of $I) at $(date -u +%T): killing the controller (pgid $CPID)"
kill -TERM -- -$CPID 2>/dev/null; sleep 3; kill -KILL -- -$CPID 2>/dev/null
RUN=$(latest_run $I); echo "run=$RUN"
vm $I "sudo cat /var/lib/docker-engine-guard/runs/$RUN/deadline.json 2>/dev/null; echo; date -u +%T"
ssh_fail=0; t0=$SECONDS
while :; do
  p=$(phase_of $I) || true
  if ! vm $I true 2>/dev/null; then ssh_fail=$((ssh_fail + 1)); echo "ssh probe FAILED at $(date -u +%T)"; fi
  case "$p" in rolled-back|rollback-partial) break ;; esac
  [ $((SECONDS - t0)) -gt 2400 ] && { echo "TIMEOUT waiting for rollback; phase=$p"; break; }
  sleep 20
done
echo "######## phase=$(phase_of $I) at $(date -u +%T) after $((SECONDS - t0))s; ssh probe failures=$ssh_fail"
echo "######## rolled-back check"; rolled_back_check $I
echo "######## C-06: confirm after the deadline"; guard_op $I confirm "$RUN"
echo "######## after the late confirm"; rolled_back_check $I | head -2
