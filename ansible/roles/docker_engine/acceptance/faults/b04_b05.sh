#!/usr/bin/env bash
# FAULTS B-04 (a crash between the commit rename and the phase update) and B-05
# (a reboot there). Injection on a confirmed host: the run's phase is put back to
# `committed` and its units disabled and stopped, which is what a confirm killed
# after the rename and before finish_post_commit leaves. Then (B-05) a reboot.
# Pass: the next converge is dispatched by the marker: confirmed.
#   b04_b05.sh <vm> b04|b05
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 CASE=$2
RUN=$(vm $I "sudo python3 -c 'import json;print(json.load(open(\"/var/lib/docker-engine-guard/confirmed\"))[\"run\"])'")
echo "######## $CASE on committed run $RUN"
vm $I "sudo bash -c 'echo committed > /var/lib/docker-engine-guard/runs/$RUN/phase; systemctl disable --now docker.socket docker.service containerd.service 2>&1 | tail -1; sync; echo phase=\$(cat /var/lib/docker-engine-guard/runs/$RUN/phase)'"
if [ "$CASE" = b05 ]; then vm $I 'sudo systemctl reboot' 2>/dev/null; sleep 20; for _ in $(seq 1 60); do vm $I true 2>/dev/null && break; sleep 5; done; echo "back at $(date -u +%T)"; sleep 20; fi
vm $I "sudo bash -c 'for u in containerd.service docker.service docker.socket; do echo \$u \$(systemctl is-enabled \$u)/\$(systemctl is-active \$u); done'"
converge $I tmp/faults/$CASE-vm$I.converge.log
vm $I "sudo bash -c 'echo phase=\$(cat /var/lib/docker-engine-guard/runs/$RUN/phase); cat /var/lib/docker-engine-guard/confirmed; echo; for u in containerd.service docker.service docker.socket; do echo \$u \$(systemctl is-enabled \$u)/\$(systemctl is-active \$u); done; iptables -S FORWARD | head -1; ls /run/docker-engine-guard/'"
