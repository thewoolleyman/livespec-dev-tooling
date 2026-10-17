#!/usr/bin/env bash
# FAULTS H-01 at the production window (no FAULTS_WINDOW override): a fresh
# baseline converges through reserve, publish, arm, start, observe, the
# controller probes and confirm. Pass: confirmed.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1
echo "######## restore guard-vm-$I"; restore $I || exit 1
converge $I tmp/faults/h01-vm$I.converge.log
vm $I "sudo bash -c 'cat /var/lib/docker-engine-guard/confirmed; echo; r=\$(ls -t /var/lib/docker-engine-guard/runs | head -1); echo run=\$r phase=\$(cat /var/lib/docker-engine-guard/runs/\$r/phase); for u in containerd.service docker.service docker.socket; do echo \$u \$(systemctl is-enabled \$u)/\$(systemctl is-active \$u); done; iptables -S FORWARD | head -1; systemctl is-active fabro-sandbox.slice'"
