#!/usr/bin/env bash
# FAULTS P-05 (the LLM health stub stops during the window) and P-06 (the
# new-SSH-session probe fails). Both inject once the run reads `observed`, so
# the failure reaches only the controller's challenge-stage probes (answer.yml),
# not the observer and not the preflight probes. Pass: the controller-side
# rescue runs `rollback`; rolled back.   p05_p06.sh <vm> p05|p06
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 CASE=$2 W=${FAULTS_WINDOW:-90} L=tmp/faults/$2-vm$1
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
FLAG=$PWD/tmp/faults/$CASE-vm$I.fail; rm -f "$FLAG"
extra=()
if [ "$CASE" = p06 ]; then
  # A wrapper that fails while the flag exists and is otherwise the inventory's own probe.
  W6=$PWD/tmp/faults/p06-ssh-vm$I.sh
  printf '#!/usr/bin/env bash\n[ -e %q ] && { echo "p06: injected failure" >&2; exit 255; }\nexec "$@"\n' "$FLAG" > "$W6"; chmod +x "$W6"
  KEY=$FAULTS_KEY PORT=$((2229 + 10 * I))
  argv=$(python3 -c 'import json,sys; print(json.dumps(sys.argv[1:]))' bash "$W6" ssh -i "$KEY" -J cwoolley@poweredge-xubuntu -p "$PORT" -o BatchMode=yes -o ConnectTimeout=15 -o ControlMaster=no -o ControlPath=none -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null guard@127.0.0.1 true)
  extra=(-e "{\"docker_engine_tailscale_ssh_argv\": $argv}")
fi
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W $(printf '%q ' "${extra[@]}")" > $L.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = observed ] || ! kill -0 $CPID 2>/dev/null; do sleep 0.5; done
echo "######## $CASE phase=$(phase_of $I) at $(date -u +%T): injecting"
if [ "$CASE" = p05 ]; then vm $I 'sudo systemctl stop local-homelab-llama-server.service; systemctl is-active local-homelab-llama-server.service'
else touch "$FLAG"; fi
wait $CPID; cat $L.converge.out
grep -aE 'failed at|Rolling back' $L.converge.log | tail -2 | cut -c1-300
rm -f "$FLAG"; [ "$CASE" = p05 ] && vm $I 'sudo systemctl start local-homelab-llama-server.service'
rolled_back_check $I
