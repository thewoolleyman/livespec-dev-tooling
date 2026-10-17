#!/usr/bin/env bash
# FAULTS M-02: a rollback-partial run. Pass: refused unless
# docker_engine_acknowledge_run=<id> is given. Run on a VM already holding one
# (R-04 leaves it). Then: an acknowledged verify while the postcondition still
# fails is refused; repaired by hand, the acknowledged verify promotes it, and
# the dead-man timer's state afterwards is reported (guard child 12, bqoany).
#   m02.sh <vm>
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=$1; RUN=$(latest_run $I); L=tmp/faults/m02-vm$I
echo "######## M-02 on run $RUN phase=$(phase_of $I)"
echo "######## 1. converge, no acknowledgement (expect refusal)"; converge $I $L.noack.log
echo "######## 2. acknowledged, postcondition still failing (expect verify refusal)"; converge $I $L.ack1.log -e docker_engine_acknowledge_run=$RUN
grep -aE 'verify (proceed|refuse)' $L.ack1.log | head -2 | cut -c1-250; echo "phase=$(phase_of $I)"
echo "######## 3. repair: the guard's own footprint-removal phase, run by the operator"
vm $I "sudo /usr/local/libexec/docker-engine-guard rollback $RUN --phase footprint-removal; echo exit=\$?; iptables -S | grep -ci docker; ip6tables -S | grep -ci docker; iptables -t nat -S | grep -c 172.17"
echo "######## 4. acknowledged verify (expect promotion to rolled-back)"; converge $I $L.ack2.log -e docker_engine_acknowledge_run=$RUN
grep -aE 'verify (proceed|refuse)' $L.ack2.log | head -2 | cut -c1-250
echo "phase=$(phase_of $I)"
echo "######## 5. dead-man timer after the promotion (finding 3 / bqoany)"; vm $I "systemctl list-units --all --plain --no-legend 'docker-engine-deadman-$RUN*'; systemctl is-active docker-engine-deadman-$RUN.timer; date -u +%FT%TZ"
echo "######## 6. next converge (classify)"; converge $I $L.next.log -e docker_engine_window_seconds=90
grep -aE '"msg": "class=' $L.next.log | head -1 | cut -c1-250
