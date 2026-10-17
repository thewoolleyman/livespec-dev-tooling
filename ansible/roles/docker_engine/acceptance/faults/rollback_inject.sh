#!/usr/bin/env bash
# Rollback-robustness driver: R-01..R-05.   rollback_inject.sh <vm> <mode> [phase]
#   kill <phase>     R-01: SIGKILL that phase's python child (not `timeout`)
#   hang <phase>     R-02: SIGSTOP that phase's python child
#   deadman          R-03: SIGKILL the dead-man's service once two phases succeeded
#   parent <phase>   R-04: SIGKILL the rollback DRIVER each time it is in <phase>
#   respawn          R-05: SIGKILL dockerd's main process right after the revoke
# A converge with a short test-only window runs to `observing`; the controller
# is killed; guest_inject.sh is armed ON the guest; then the dead-man's own
# service is started at once (the identical unit and code the timer starts at
# the deadline, without the ~15 min wait). Later firings come from the timer.
# FAULTS_NO_RESTORE=1 reuses the VM as it stands.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 MODE=$2 PH=${3:--} W=${FAULTS_WINDOW:-90}
TAG=$MODE-$PH-vm$I; L=tmp/faults/$TAG
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 1; done
RUN=$(latest_run $I); G=/var/lib/docker-engine-guard/runs/$RUN
[ "$(phase_of $I)" = observing ] || { echo "######## $TAG never reached observing: $(phase_of $I)"; tail -5 $L.converge.out; exit 1; }
kill -TERM -- -$CPID 2>/dev/null; sleep 2; kill -KILL -- -$CPID 2>/dev/null
echo "######## $TAG run=$RUN: controller killed at $(date -u +%T)"
vm $I "sudo tee /run/guest_inject.sh >/dev/null" < ansible/roles/docker_engine/acceptance/faults/guest_inject.sh
vm $I "sudo systemd-run --unit=fault-inject-$RUN --collect bash /run/guest_inject.sh $MODE $PH $RUN && sleep 1 && sudo systemctl start --no-block docker-engine-deadman-$RUN.service && echo dead-man service started \$(date -u +%T)"
t0=$SECONDS; ssh_fail=0
while :; do
  p=$(phase_of $I) || true
  vm $I true 2>/dev/null || { ssh_fail=$((ssh_fail+1)); echo "ssh FAILED $(date -u +%T)"; }
  case "$p" in rolled-back) break ;; rollback-partial) [ "$MODE" = hang ] || [ "$MODE" = parent ] || [ "$MODE" = kill ] || break ;; esac
  # a partial outcome after an injected phase is re-tried by the timer's next firing; give it the time
  [ $((SECONDS - t0)) -gt 1500 ] && { echo "TIMEOUT phase=$p"; break; }
  sleep 3
done
echo "######## $TAG phase=$(phase_of $I) after $((SECONDS - t0))s; ssh failures=$ssh_fail"
echo "-- injector:"; vm $I "sudo cat /run/fault-inject-$RUN.log"
echo "-- phase records:"; vm $I "sudo bash -c 'cd $G/rollback 2>/dev/null && for f in *; do printf \"%s=%s \" \$f \$(cat \$f); done'"; echo
echo "-- dead-man journal:"; vm $I "sudo journalctl -u 'docker-engine-deadman-$RUN*' --no-pager -o short-iso | grep -E 'rollback (proceed|refuse)|Started docker-engine-deadman.*service|Main process|Failed|killed' | tail -14"
rolled_back_check $I
