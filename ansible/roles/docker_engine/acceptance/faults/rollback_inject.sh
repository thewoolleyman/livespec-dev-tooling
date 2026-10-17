#!/usr/bin/env bash
# Rollback-robustness driver: R-01..R-05 and P-01.   rollback_inject.sh <vm> <mode> [phase]
# A converge with a short test-only window (none of these cases exercises the
# window) runs to `observing`; the controller is killed so the dead-man's own
# rollback fires (P-01 keeps it alive), then one injection:
#   kill <phase>     R-01: SIGKILL that phase's python child once (not `timeout`)
#   hang <phase>     R-02: SIGSTOP that phase's python child once
#   deadman          R-03: SIGKILL the dead-man's service once two phases succeeded
#   parent <phase>   R-04: SIGKILL the rollback DRIVER whenever it is in <phase>
#   respawn          R-05: SIGKILL dockerd's main process once start permission is revoked
#   sample           P-01: flip FORWARD to DROP while observing, so a sample fails
# --no-restore reuses the VM as it is (a re-run after a rollback is itself the
# path under test, and it saves the restore).
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 MODE=$2 PH=${3:-} W=${FAULTS_WINDOW:-90}
TAG=$MODE${PH:+-$PH}-vm$I; L=tmp/faults/$TAG
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 1; done
RUN=$(latest_run $I); G=/var/lib/docker-engine-guard/runs/$RUN
echo "######## $TAG run=$RUN phase=$(phase_of $I) at $(date -u +%T)"
if [ "$MODE" = sample ]; then vm $I 'sudo iptables -P FORWARD DROP'; echo "FORWARD -> DROP at $(date -u +%T)"
else kill -TERM -- -$CPID 2>/dev/null; sleep 2; kill -KILL -- -$CPID 2>/dev/null; echo "controller killed $(date -u +%T)"; fi
# The phase CHILD is the python process whose argv carries `--phase <p>` and does not start with `timeout`.
child="for p in \$(pgrep -f \"docker_engine_guard.py rollback $RUN .*--phase $PH\$\"); do echo \$p; done"
DONE=0
inject() {
  case $MODE in
    kill) [ $DONE = 1 ] && return; o=$(vm $I "sudo bash -c '$child' | head -1"); [ -n "$o" ] && { vm $I "sudo kill -KILL $o"; echo "killed $PH child $o $(date -u +%T)"; DONE=1; } ;;
    hang) [ $DONE = 1 ] && return; o=$(vm $I "sudo bash -c '$child' | head -1"); [ -n "$o" ] && { vm $I "sudo kill -STOP $o"; echo "stopped $PH child $o $(date -u +%T)"; DONE=1; } ;;
    deadman) [ $DONE = 1 ] && return; n=$(vm $I "sudo bash -c 'ls $G/rollback 2>/dev/null | grep -c \"\\.success\$\"'"); [ "${n:-0}" -ge 2 ] && { vm $I "sudo systemctl kill -s KILL docker-engine-deadman-$RUN.service"; echo "killed dead-man service after $n successes $(date -u +%T)"; DONE=1; } ;;
    parent) o=$(vm $I "sudo bash -c '$child' | head -1"); [ -n "$o" ] && { d=$(vm $I "sudo bash -c 'for p in \$(pgrep -f \"docker_engine_guard.py rollback $RUN\"); do tr \"\\0\" \" \" </proc/\$p/cmdline | grep -q -- --phase || echo \$p; done' | head -1"); [ -n "$d" ] && { vm $I "sudo kill -KILL $d"; echo "killed driver $d in $PH (attempts $(vm $I "sudo cat $G/rollback/$PH.attempts 2>/dev/null")) $(date -u +%T)"; }; } ;;
    respawn) [ $DONE = 1 ] && return; o=$(vm $I "sudo bash -c '[ ! -e /run/docker-engine-guard/allow-start ] && systemctl show -p MainPID --value docker.service'"); [ -n "$o" ] && [ "$o" != 0 ] && { vm $I "sudo kill -KILL $o"; echo "SIGKILLed dockerd $o after revoke $(date -u +%T)"; DONE=1; } ;;
  esac
}
ssh_fail=0; t0=$SECONDS; started_seen=0
while :; do
  p=$(phase_of $I) || true
  vm $I true 2>/dev/null || { ssh_fail=$((ssh_fail+1)); echo "ssh FAILED $(date -u +%T)"; }
  [ "$MODE" != sample ] && inject
  [ "$MODE" = respawn ] && [ $DONE = 1 ] && [ "$(vm $I 'systemctl is-active docker.service')" = active ] && { started_seen=1; echo "docker.service ACTIVE after the kill $(date -u +%T)"; }
  case "$p" in rolled-back) break ;; rollback-partial) [ "$MODE" = parent ] || [ "$MODE" = hang ] || break ;; esac
  [ $((SECONDS - t0)) -gt 2700 ] && { echo "TIMEOUT phase=$p"; break; }
  sleep 1
done
echo "######## $TAG phase=$(phase_of $I) after $((SECONDS - t0))s; ssh failures=$ssh_fail; respawn-active-seen=$started_seen"
vm $I "sudo bash -c 'cd $G/rollback 2>/dev/null && for f in *; do echo \$f=\$(cat \$f); done'" | tr '\n' ' '; echo
vm $I "sudo journalctl -u 'docker-engine-deadman-$RUN*' --no-pager -o short-iso | grep -E 'rollback|Started|Main process|killed|Failed' | tail -12"
rolled_back_check $I
[ "$MODE" = sample ] && wait $CPID; true
