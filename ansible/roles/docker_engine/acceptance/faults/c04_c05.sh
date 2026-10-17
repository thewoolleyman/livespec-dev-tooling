#!/usr/bin/env bash
# FAULTS C-05 (a duplicate `start` after rollback began) and C-04 (a delayed
# `publish` after a newer reservation), on guard-vm-3's rolled-back P-04 run.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
I=3
OLD=$(latest_run $I); echo "old run=$OLD phase=$(phase_of $I)"
echo "######## C-05: duplicate start of the rolled-back run"; guard_op $I start "$OLD"
NEW=rc04$(date +%Y%m%d%H%M%S)
echo "######## C-04: a newer reservation $NEW"; guard_op $I reserve "$NEW"
echo "######## C-04: the delayed publish of the old run"; guard_op $I publish "$OLD"
echo "######## the newer reservation is unaffected"; vm $I "sudo bash -c 'for r in /var/lib/docker-engine-guard/runs/*; do echo \$(basename \$r) \$(cat \$r/phase); done'"
echo "######## release the newer reservation (rollback of a run with no snapshot)"; guard_op $I rollback "$NEW"
rolled_back_check $I
