#!/usr/bin/env bash
# bootstrap.sh — first-touch setup of this checkout: the `just bootstrap` recipe.
#
# The host's bare python3 is checked against requires-python FIRST
# (check-host-python3.sh), before `uv run` can resolve or download an
# interpreter; then the package's own local first-touch reconcile verb runs
# (livespec_dev_tooling.fleet.local_reconcile). Governed by
# SPECIFICATION/non-functional-requirements.md, "Developer host platforms".
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
"$root/scripts/just/check-host-python3.sh" "$root"
exec uv run python -m livespec_dev_tooling.fleet.local_reconcile
