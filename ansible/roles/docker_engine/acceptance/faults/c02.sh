#!/usr/bin/env bash
# FAULTS C-02: a second controller's `reserve` during each phase of a healthy run.
# Pass: every one refused; the run is unaffected (confirmed).
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=1
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I tmp/faults/c02.converge.log" > tmp/faults/c02.converge.out 2>&1 &
CPID=$!
declare -A tried
while kill -0 $CPID 2>/dev/null; do
  p=$(phase_of $I)
  case "$p" in
    reserved|publishing|published|armed|started|observing|observed)
      if [ -z "${tried[$p]:-}" ]; then tried[$p]=1; echo "######## phase=$p: second controller reserves"; guard_op $I reserve "rc02x$(date +%H%M%S)" ; fi ;;
  esac
  sleep 2
done
cat tmp/faults/c02.converge.out
echo "######## phases a second reserve was tried in: ${!tried[*]}"
echo "######## the run after"; vm $I 'sudo bash -c "ls /var/lib/docker-engine-guard/runs; for r in /var/lib/docker-engine-guard/runs/*; do echo \$(basename \$r) \$(cat \$r/phase); done; cat /var/lib/docker-engine-guard/confirmed"'
