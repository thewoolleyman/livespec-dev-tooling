#!/usr/bin/env bash
set -euo pipefail

# Resolve incident mode before any gate work (livespec-dev-tooling-6bmta2). The
# presence test is the installed hook's prefilter and decides nothing: unset, the
# body below runs unchanged; present, the shared boundary
# (livespec_dev_tooling/incident_gate_entry.py) parses and decides, and only its
# 75 continues. Every other status, including an unavailable boundary, refuses.
if [ -n "${EXPEDITED_INCIDENT_RESPONSE:-}${EXPEDITED_INCIDENT_RESPONSE_REVERT:-}${LIVESPEC_INCIDENT_CONTEXT:-}${LIVESPEC_INCIDENT_AUTHORITY_QUERY:-}" ]; then
    incident_status=0
    uv run --no-sync python -m livespec_dev_tooling.incident_gate_entry check-changed || incident_status=$?
    [ "$incident_status" -eq 75 ] || exit $((incident_status == 0 ? 78 : incident_status))
fi

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
