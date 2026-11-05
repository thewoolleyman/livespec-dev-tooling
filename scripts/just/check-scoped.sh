#!/usr/bin/env bash
set -euo pipefail

# Resolve incident mode before any gate work (livespec-dev-tooling-6bmta2). The
# presence test is the installed hook's prefilter and decides nothing: unset, the
# body below runs unchanged; present, the shared boundary
# (livespec_dev_tooling/incident_gate_entry.py) parses and decides, and only its
# 75 continues. Every other status, including an unavailable boundary, refuses.
if [ -n "${EXPEDITED_INCIDENT_RESPONSE:-}${EXPEDITED_INCIDENT_RESPONSE_REVERT:-}${LIVESPEC_INCIDENT_CONTEXT:-}${LIVESPEC_INCIDENT_AUTHORITY_QUERY:-}" ]; then
    incident_status=0
    uv run --no-sync python -m livespec_dev_tooling.incident_gate_entry check-scoped || incident_status=$?
    [ "$incident_status" -eq 75 ] || exit $((incident_status == 0 ? 78 : incident_status))
fi

upstream="origin/master"
changeset=$(git diff --name-only "${upstream}...HEAD")
if [[ -z "$changeset" ]]; then
    echo ":: check-scoped: no changes vs ${upstream}; nothing to gate"
    exit 0
fi

py_changed=$(echo "$changeset" | grep -E '\.py$' || true)
if [[ -z "$py_changed" ]]; then
    echo ":: check-scoped: no .py changes vs ${upstream} (change class: doc/config/deletion)"
    echo ":: running fast doc-only subset; CI runs the full matrix as the load-bearing gate"
    just check-pre-commit-doc-only
    exit $?
fi

echo ":: check-scoped: .py changes detected vs ${upstream}: running full check aggregate"
just check
