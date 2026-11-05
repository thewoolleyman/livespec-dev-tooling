#!/usr/bin/env bash
set -euo pipefail

# Resolve incident mode before any gate work (livespec-dev-tooling-wjmre6). The
# presence test is the installed hook's prefilter and decides nothing: unset, the
# body below runs unchanged; present, the shared boundary
# (livespec_dev_tooling/incident_gate_entry.py) parses and decides, and only its
# 75 continues. Every other status, including an unavailable boundary, refuses.
if [ -n "${EXPEDITED_INCIDENT_RESPONSE:-}${EXPEDITED_INCIDENT_RESPONSE_REVERT:-}${LIVESPEC_INCIDENT_CONTEXT:-}${LIVESPEC_INCIDENT_AUTHORITY_QUERY:-}" ]; then
    incident_status=0
    uv run --no-sync python -m livespec_dev_tooling.incident_gate_entry lint-autofix-staged || incident_status=$?
    [ "$incident_status" -eq 75 ] || exit $((incident_status == 0 ? 78 : incident_status))
fi

staged=$(git diff --cached --name-only --diff-filter=AM | grep -E '\.py$' || true)
if [[ -z "$staged" ]]; then
    exit 0
fi

echo "$staged" | xargs uv run ruff check --fix --exit-zero
echo "$staged" | xargs uv run ruff format
echo "$staged" | xargs git add
