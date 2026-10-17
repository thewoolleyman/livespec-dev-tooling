#!/usr/bin/env bash
# FAULTS C-07: `confirm` retried after a crash past the commit point, more than 120 s later.
# Injection: on a confirmed host, the run's phase is put back to `committed` (the
# state a confirm killed after the commit rename and before its last phase write
# leaves), then confirm is retried 130 s later. Pass: it finishes; confirmed.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=1
RUN=$(latest_run $I); echo "run=$RUN"
vm $I "sudo bash -c 'cat /var/lib/docker-engine-guard/confirmed; echo; echo committed > /var/lib/docker-engine-guard/runs/$RUN/phase; sync; echo phase=\$(cat /var/lib/docker-engine-guard/runs/$RUN/phase)'"
echo "######## waiting 130 s"; sleep 130
echo "######## retry confirm"; guard_op $I confirm "$RUN"
echo "######## after"; vm $I "sudo bash -c 'echo phase=\$(cat /var/lib/docker-engine-guard/runs/$RUN/phase); cat /var/lib/docker-engine-guard/confirmed; echo; for u in containerd.service docker.service docker.socket; do echo \$u \$(systemctl is-enabled \$u)/\$(systemctl is-active \$u); done; iptables -S FORWARD | head -1'"
