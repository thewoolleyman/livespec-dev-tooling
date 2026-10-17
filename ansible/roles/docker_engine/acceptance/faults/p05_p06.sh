#!/usr/bin/env bash
# FAULTS P-05 (the LLM health stub stopped during the window) and P-06 (the
# new-SSH-session probe fails). Pass for both: the controller-side rescue runs
# `rollback`; rolled back.   p05_p06.sh <vm> p05|p06
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 CASE=$2 W=${FAULTS_WINDOW:-90}
echo "######## restore guard-vm-$I"; restore $I || exit 1
if [ "$CASE" = p06 ]; then
  # The probe's argv is host_vars; a probe that cannot open a session is the
  # injection, so the controller sees exactly a failing new-session probe.
  converge $I tmp/faults/p06.converge.log -e docker_engine_window_seconds=$W -e '{"docker_engine_tailscale_ssh_argv": ["false"], "docker_engine_lan_fallback_ssh_argv": ["false"]}'
else
  setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I tmp/faults/p05.converge.log -e docker_engine_window_seconds=$W" > tmp/faults/p05.converge.out 2>&1 &
  CPID=$!
  until [ "$(phase_of $I)" = observing ] || ! kill -0 $CPID 2>/dev/null; do sleep 2; done
  echo "######## observing at $(date -u +%T): stopping the LLM health stub"
  vm $I 'sudo systemctl stop local-homelab-llama-server.service; systemctl is-active local-homelab-llama-server.service'
  wait $CPID; cat tmp/faults/p05.converge.out
  grep -aE '"msg": "(Run |run=)' tmp/faults/p05.converge.log | tail -2 | cut -c1-400
fi
grep -aE 'failed at|Rolling back' tmp/faults/$CASE.converge.log | tail -2 | cut -c1-300
rolled_back_check $I
