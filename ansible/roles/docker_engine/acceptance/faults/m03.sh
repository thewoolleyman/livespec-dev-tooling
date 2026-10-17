#!/usr/bin/env bash
# FAULTS M-03: foreign /var/lib/docker state with no `installed` record.
# Pass: refused; nothing is touched.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=2
echo "######## inject: foreign /var/lib/docker state on guard-vm-$I"; vm $I 'sudo mkdir -p /var/lib/docker/image && echo foreign | sudo tee /var/lib/docker/foreign-marker >/dev/null; sudo ls -A /var/lib/docker'
echo "######## footprint before"; footprint $I | tee tmp/faults/m03.before
echo "######## converge"; converge $I tmp/faults/m03.converge.log
echo "######## footprint after"; footprint $I | tee tmp/faults/m03.after
diff tmp/faults/m03.before tmp/faults/m03.after >/dev/null && echo "HOST UNTOUCHED" || { echo "HOST CHANGED:"; diff tmp/faults/m03.before tmp/faults/m03.after; }
grep -nE "^TASK" tmp/faults/m03.converge.log | tail -3
