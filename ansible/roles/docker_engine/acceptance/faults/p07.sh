#!/usr/bin/env bash
# FAULTS P-07: a must-stay-running unit (k3s-agent) is inactive before the change.
# Pass: the role refuses before any change; the host is untouched.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=1
echo "######## inject: stop k3s-agent on guard-vm-$I"; vm $I 'sudo systemctl stop k3s-agent.service; systemctl is-active k3s-agent.service'
echo "######## footprint before"; footprint $I | tee tmp/faults/p07.before
echo "######## converge"; converge $I tmp/faults/p07.converge.log
echo "######## footprint after"; footprint $I | tee tmp/faults/p07.after
diff tmp/faults/p07.before tmp/faults/p07.after >/dev/null && echo "HOST UNTOUCHED" || { echo "HOST CHANGED:"; diff tmp/faults/p07.before tmp/faults/p07.after; }
grep -nE "^TASK" tmp/faults/p07.converge.log | tail -3
echo "######## restore: start k3s-agent"; vm $I 'sudo systemctl start k3s-agent.service; systemctl is-active k3s-agent.service'
