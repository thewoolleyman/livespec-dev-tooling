#!/usr/bin/env bash
# Generic rollback-robustness driver: R-01, R-02, R-03, R-04, R-05 and P-01.
#   rollback_inject.sh <vm> <mode>
# A converge with a short test-only window (none of these cases exercises the
# window) runs to `observing`; then:
#   kill     R-01: SIGKILL every rollback phase child as it appears (one firing)
#   hang     R-02: SIGSTOP every rollback phase child as it appears
#   deadman  R-03: SIGKILL the dead-man's rollback service once two phases have succeeded
#   parent   R-04: SIGKILL the rollback driver each time it enters footprint-removal
#   respawn  R-05: during rollback, try to start docker.service every second
#   sample   P-01: during observing (controller alive), flip FORWARD to DROP so a sample fails
# Pass for every mode: the run ends rolled-back (or rollback-partial where the
# case says so); guest SSH answers throughout.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 MODE=$2 TAG=${MODE}-vm$1 W=${FAULTS_WINDOW:-90}
log=tmp/faults/$TAG
echo "######## restore guard-vm-$I"; restore $I || exit 1
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $log.converge.log -e docker_engine_window_seconds=$W" > $log.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 2; done
RUN=$(latest_run $I); echo "######## run=$RUN phase=$(phase_of $I) at $(date -u +%T)"
if [ "$MODE" = sample ]; then
  vm $I 'sudo iptables -P FORWARD DROP'; echo "FORWARD set to DROP at $(date -u +%T)"
else
  kill -TERM -- -$CPID 2>/dev/null; sleep 3; kill -KILL -- -$CPID 2>/dev/null; echo "controller killed"
fi
G=/var/lib/docker-engine-guard/runs/$RUN
inject() { # one pass of the injection, on the guest
  case $MODE in
    kill) vm $I "sudo bash -c 'for p in \$(pgrep -f \"rollback $RUN .*--phase\"); do a=\$(tr \"\\0\" \" \" </proc/\$p/cmdline 2>/dev/null); case \$a in timeout*) kill -KILL \$p && echo \"killed \${a##*--phase }\";; esac; done'" ;;
    hang) vm $I "sudo bash -c 'for p in \$(pgrep -f \"rollback $RUN .*--phase\"); do s=\$(awk \"{print \\\$3}\" /proc/\$p/stat 2>/dev/null); a=\$(tr \"\\0\" \" \" </proc/\$p/cmdline 2>/dev/null); case \$a in timeout*) ;; *) [ \"\$s\" != T ] && kill -STOP \$p && echo \"stopped \${a##*--phase }\";; esac; done'" ;;
    deadman) [ -z "${DONE:-}" ] && [ "$(vm $I "sudo ls $G/rollback 2>/dev/null | grep -c succeeded")" -ge 2 ] && { vm $I "sudo systemctl kill -s KILL docker-engine-deadman-$RUN.service; echo killed dead-man service"; DONE=1; } ;;
    parent) vm $I "sudo bash -c 'pgrep -f \"rollback $RUN .*--phase footprint-removal\" >/dev/null && for p in \$(pgrep -f \"docker-engine-guard rollback $RUN\"); do a=\$(tr \"\\0\" \" \" </proc/\$p/cmdline); case \$a in *--phase*|timeout*) ;; *) kill -KILL \$p && echo \"killed driver \$p at footprint-removal (attempts \$(cat $G/rollback/footprint-removal.attempts 2>/dev/null))\";; esac; done'" ;;
    respawn) vm $I 'sudo systemctl start --no-block docker.service 2>&1 | head -1; echo "docker.service=$(systemctl is-active docker.service)"' | sort -u ;;
  esac
}
ssh_fail=0; t0=$SECONDS
while :; do
  p=$(phase_of $I) || true
  vm $I true 2>/dev/null || { ssh_fail=$((ssh_fail+1)); echo "ssh FAILED $(date -u +%T)"; }
  case "$p" in rolling-back|observing|started|*) [ "$MODE" != sample ] && inject ;; esac
  case "$p" in rolled-back) break ;; rollback-partial) [ "$MODE" = kill ] || [ "$MODE" = hang ] || [ "$MODE" = parent ] || break ;; esac
  [ $((SECONDS - t0)) -gt 3000 ] && { echo "TIMEOUT phase=$p"; break; }
  sleep 1
done
echo "######## phase=$(phase_of $I) after $((SECONDS - t0))s at $(date -u +%T); ssh failures=$ssh_fail"
vm $I "sudo bash -c 'cd $G/rollback 2>/dev/null && for f in *; do echo \$f=\$(cat \$f); done; cat $G/outcome* 2>/dev/null'" | head -40
vm $I "sudo journalctl -u 'docker-engine-deadman-$RUN*' -u 'docker-engine-guard-rollback-$RUN*' --no-pager -o short-iso | grep -vE 'Deactivated|Consumed' | tail -25"
rolled_back_check $I
[ "$MODE" = sample ] && wait $CPID; true
