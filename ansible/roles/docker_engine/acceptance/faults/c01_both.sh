#!/usr/bin/env bash
# FAULTS C-01 in both orders on one VM: confirm first, then the dead-man first.
bash "$(dirname "$0")/c01_p03.sh" "$1" confirm-first
bash "$(dirname "$0")/c01_p03.sh" "$1" deadman-first  # restores: a confirmed outcome leaves a committed host
