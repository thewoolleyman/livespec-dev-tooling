#!/usr/bin/env bash
# chain.sh <vm> "<mode> <phase>" ["<mode> <phase>" ...]: run rollback_inject cases
# back to back on one VM, restoring only before the first.
set -uo pipefail
I=$1; shift; first=1
for c in "$@"; do
  if [ $first = 1 ]; then FAULTS_NO_RESTORE= bash "$(dirname "$0")/rollback_inject.sh" "$I" $c; first=0
  else FAULTS_NO_RESTORE=1 bash "$(dirname "$0")/rollback_inject.sh" "$I" $c; fi
done
