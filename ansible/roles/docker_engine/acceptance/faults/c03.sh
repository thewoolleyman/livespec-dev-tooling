#!/usr/bin/env bash
# FAULTS C-03: SIGSTOP each subcommand while it holds the lock. Pass: it is
# killed within its budget plus 30 s, and the lock is released.
#   c03.sh <vm> <op>   op: reserve | arm | confirm | deadman
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 OP=$2 W=${FAULTS_WINDOW:-90} L=tmp/faults/c03-$2-vm$1
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
vm $I "sudo tee /run/guest_inject.sh >/dev/null" < ansible/roles/docker_engine/acceptance/faults/guest_inject.sh
if [ "$OP" != deadman ]; then
  vm $I "sudo systemd-run --unit=fault-inject-c03-$OP --collect bash /run/guest_inject.sh sigstop docker-engine-guard-$OP- c03-$OP"
  converge $I $L.converge.log -e docker_engine_window_seconds=$W
else
  setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
  CPID=$!
  until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 1; done
  RUN=$(latest_run $I); kill -TERM -- -$CPID 2>/dev/null; sleep 2; kill -KILL -- -$CPID 2>/dev/null
  # wait for the killed controller's observer to finish (it holds the lock for the window)
  until ! vm $I "systemctl is-active -q docker-engine-guard-observe.service"; do sleep 3; done
  vm $I "sudo systemd-run --unit=fault-inject-c03-deadman --collect bash /run/guest_inject.sh sigstop docker-engine-deadman-$RUN.service c03-deadman && sleep 1 && sudo systemctl start --no-block docker-engine-deadman-$RUN.service"
  vm $I "systemctl show -p Type -p TimeoutStartUSec docker-engine-deadman-$RUN.service"
  until vm $I "sudo grep -qE 'lock released|LOCK STILL HELD|TIMEOUT' /run/fault-inject-c03-deadman.log 2>/dev/null"; do sleep 10; done
fi
until vm $I "sudo grep -qE 'lock released|LOCK STILL HELD|TIMEOUT' /run/fault-inject-c03-$OP.log 2>/dev/null"; do sleep 5; done
echo "######## C-03 $OP:"; vm $I "sudo cat /run/fault-inject-c03-$OP.log"
echo "phase=$(phase_of $I)"
