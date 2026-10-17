#!/usr/bin/env bash
# FAULTS C-01 (confirm and the deadline firing concurrently, in both orders; pass:
# exactly one outcome, never both) and P-03 (the controller killed after the
# observer's challenge; pass: the deadline rolls the run back).
#   c01_p03.sh <vm> confirm-first|deadman-first|p03
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 CASE=$2 W=${FAULTS_WINDOW:-90} L=tmp/faults/$2-vm$1
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 1; done
RUN=$(latest_run $I); G=/var/lib/docker-engine-guard/runs/$RUN
echo "######## $CASE run=$RUN observing at $(date -u +%T)"
if [ "$CASE" = p03 ]; then
  until [ "$(phase_of $I)" = observed ] || ! kill -0 $CPID 2>/dev/null; do sleep 0.5; done
  # The challenge is issued at `observed`; let the controller read it, then lose it.
  until vm $I "sudo test -e /run/docker-engine-guard/challenge" || ! kill -0 $CPID 2>/dev/null; do sleep 0.5; done
  kill -KILL -- -$CPID 2>/dev/null; echo "controller killed after the challenge at $(date -u +%T); waiting for the deadline"
  vm $I "sudo cat $G/deadline.json"; echo
  t0=$SECONDS; until case "$(phase_of $I)" in rolled-back|rollback-partial) true;; *) false;; esac || [ $((SECONDS-t0)) -gt 2400 ]; do sleep 10; done
  echo "######## p03 phase=$(phase_of $I) $((SECONDS-t0))s after the kill"
else
  vm $I "sudo tee /run/guest_inject.sh >/dev/null" < ansible/roles/docker_engine/acceptance/faults/guest_inject.sh
  vm $I "sudo systemd-run --unit=fault-inject-$RUN --collect bash /run/guest_inject.sh race-$CASE - $RUN"
  wait $CPID; tail -3 $L.converge.out
  t0=$SECONDS; until case "$(phase_of $I)" in confirmed|rolled-back|rollback-partial) true;; *) false;; esac || [ $((SECONDS-t0)) -gt 600 ]; do sleep 3; done
  echo "-- injector:"; vm $I "sudo cat /run/fault-inject-$RUN.log"
  echo "######## C-01 $CASE phase=$(phase_of $I) marker=$(vm $I "sudo cat /var/lib/docker-engine-guard/confirmed 2>/dev/null || echo none")"
  vm $I "sudo journalctl -u 'docker-engine-deadman-$RUN*' -u 'docker-engine-guard-confirm-$RUN*' --no-pager -o cat | grep -E '(rollback|confirm) (proceed|refuse|noop)' | tail -6"
  vm $I "sudo bash -c 'for u in containerd.service docker.service docker.socket; do echo \$u \$(systemctl is-enabled \$u)/\$(systemctl is-active \$u); done; ls /run/docker-engine-guard'"
fi
rolled_back_check $I
