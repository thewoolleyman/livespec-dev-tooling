"""Regression coverage for the stand-in proxy readiness deadline boundary."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXIT_TESTS = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job-exit-tests.sh"
)


def test_stand_in_proxy_readiness_refuses_a_zero_remaining_budget_before_http() -> None:
    """Crossing the deadline after the loop predicate must not start curl.

    Bash's DEBUG trap fires before the remaining-budget assignment.  Advancing
    ``SECONDS`` there creates the formerly unbounded zero-budget call without
    relying on scheduler timing.  A fake ``timeout`` records any attempted HTTP
    command, letting the assertion distinguish refusing the expired budget from
    merely allowing its outer deadline to end the loop later.

    The trap advances ``SECONDS`` to the helper's own ``deadline`` (it runs in
    the helper's dynamic scope) rather than to a fixed value.  ``SECONDS``
    counts whole wall-clock seconds from its last assignment, so it can tick
    between the reset below and the helper's deadline calculation; a fixed
    ``SECONDS=1`` then left one second of budget and the helper legitimately
    issued attempts (livespec-dev-tooling-2yn5qh).  The 30 s budget keeps the
    first loop predicate true however late the helper starts.
    """
    script = r"""
set -u
helper="$(sed -n '/^wait_for_stand_in_proxy() {/,/^}/p' "$1")"
eval "${helper}"
failures=0
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }
scratch="$(mktemp -d)"
attempts="${scratch}/attempts"
trap 'rm -rf "${scratch}"' EXIT
printf '%s\n' '#!/bin/sh' 'printf "%s\\n" "$*" >> "${READINESS_ATTEMPTS}"' 'exit 1' > "${scratch}/timeout"
chmod 755 "${scratch}/timeout"
SECONDS=0
crossed=0
set -T
trap '
  case "${BASH_COMMAND}" in
    remaining=*)
      if [ "${crossed}" -eq 0 ]; then
        SECONDS="${deadline}"
        crossed=1
      fi
      ;;
  esac
' DEBUG
if PATH="${scratch}:${PATH}" READINESS_ATTEMPTS="${attempts}" STAND_IN_PROXY_READY_DEADLINE_SECONDS=30 \
  wait_for_stand_in_proxy 43210; then
  readiness_status=0
else
  readiness_status=$?
fi
trap - DEBUG
if [ "${crossed}" -ne 1 ]; then
  printf 'did not cross the deadline before remaining-budget calculation\n' >&2
  exit 2
fi
if [ "${readiness_status}" -ne 1 ]; then
  printf 'readiness returned %s instead of failure\n' "${readiness_status}" >&2
  exit 3
fi
if [ -s "${attempts}" ]; then
  printf 'readiness started an HTTP attempt after its budget expired: %s\n' "$(cat "${attempts}")" >&2
  exit 4
fi
"""
    completed = subprocess.run(
        ["bash", "-c", script, "--", str(_EXIT_TESTS)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert (
        "FAIL  the stand-in proxy on port 43210 never answered HTTP within 30 s" in completed.stdout
    )
