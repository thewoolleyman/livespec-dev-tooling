#!/usr/bin/env bash
# FAULTS M-01: packages installed by this role's audited set, not confirmed (the P-04
# run rolled back, and rollback never purges packages). Pass: resumed, then
# confirmed or rolled back.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=3
echo "######## before"; vm $I "sudo bash -c 'dpkg-query -W -f=\"\${Package} \${Status}\n\" docker.io containerd runc 2>/dev/null; for r in /var/lib/docker-engine-guard/runs/*; do echo \$(basename \$r) \$(cat \$r/phase); done'"
converge $I tmp/faults/m01.converge.log
grep -E '"msg": "class=' tmp/faults/m01.converge.log | head -2 | cut -c1-300
echo "######## after"; vm $I "sudo bash -c 'for r in /var/lib/docker-engine-guard/runs/*; do echo \$(basename \$r) \$(cat \$r/phase); done; cat /var/lib/docker-engine-guard/confirmed 2>/dev/null || echo no-marker'"
