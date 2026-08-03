#!/usr/bin/env bash
set -euo pipefail

mapfile -t changed < <(just changed-files)
if [[ "${#changed[@]}" -eq 0 ]]; then
    echo ":: check-changed: no changed .py vs origin/master (and none staged); nothing to gate"
    echo ":: the authoritative full gate remains 'just check' (run at pre-push + CI)"
    exit 0
fi

echo ":: check-changed: scoping the test subset + per-file coverage gate to ${#changed[@]} changed .py:"
printf '   %s\n' "${changed[@]}"
echo ":: INNER-LOOP ONLY - 'just check' runs the FULL suite/AST scans at pre-push + CI"
just check-check-coverage-incremental --paths "${changed[@]}"
