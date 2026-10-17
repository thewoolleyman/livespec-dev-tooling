#!/usr/bin/env bash
# FAULTS C-10: a delayed `arm`. The controller is frozen (SIGSTOP of its whole
# process group) for 120 s once the run reads `published`, then resumed, so its
# arm runs late. Pass: the dead-man timer elapses at the RECORDED deadline, not
# 120 s later: arm arms the remaining time (_docker_engine_guard_ops.py:188).
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1 W=${FAULTS_WINDOW:-90} L=tmp/faults/c10-vm$1
[ "${FAULTS_NO_RESTORE:-}" = 1 ] || { echo "######## restore guard-vm-$I"; restore $I || exit 1; }
setsid bash -c "source ansible/roles/docker_engine/acceptance/faults/lib.sh; converge $I $L.converge.log -e docker_engine_window_seconds=$W" > $L.converge.out 2>&1 &
CPID=$!
until [ "$(phase_of $I)" = published ] || ! kill -0 $CPID 2>/dev/null; do sleep 0.3; done
RUN=$(latest_run $I); G=/var/lib/docker-engine-guard/runs/$RUN
kill -STOP -- -$CPID; echo "######## C-10 run=$RUN: controller frozen at published $(date -u +%T)"
sleep 120; kill -CONT -- -$CPID; echo "controller resumed $(date -u +%T)"
until [ "$(phase_of $I)" != published ] || ! kill -0 $CPID 2>/dev/null; do sleep 0.3; done; sleep 2
vm $I "sudo bash -c 'echo deadline: \$(cat $G/deadline.json); echo now_monotonic: \$(cut -d\" \" -f1 /proc/uptime); systemctl show docker-engine-deadman-$RUN.timer -p NextElapseUSecMonotonic -p LastTriggerUSecMonotonic; systemctl list-timers --all --no-pager docker-engine-deadman-$RUN.timer | head -2'"
python3 - "$(vm $I "sudo cat $G/deadline.json")" "$(vm $I "systemctl show docker-engine-deadman-$RUN.timer -p NextElapseUSecMonotonic --value")" <<'PY'
import json, sys, re
d = json.loads(sys.argv[1])["monotonic"]
v = sys.argv[2].strip()
units = {"d": 86400, "h": 3600, "min": 60, "s": 1, "ms": 1e-3, "us": 1e-6}
secs = sum(float(n) * units[u] for n, u in re.findall(r"([\d.]+)\s*(d|h|min|ms|us|s)", v)) if not v.isdigit() else int(v) / 1e6
print(f"C-10: recorded deadline {d:.1f}s monotonic; timer next elapse {secs:.1f}s; difference {secs - d:+.1f}s -> {'PASS' if abs(secs - d) <= 5 else 'FAIL'}")
PY
wait $CPID; tail -2 $L.converge.out; echo "phase=$(phase_of $I)"
