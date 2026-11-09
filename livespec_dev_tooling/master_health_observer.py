"""Ask the protected incident observer who owns one failed master action.

The ``master_health_*`` decision modules deliberately stay network-free, and a
test enforces that. This is their workflow-side transport: it asks the observer
before the reconciler's rerun, classification or revert step runs, and prints
the observer's exact ownership answer for the workflow to act on.

The three outcomes, which the workflow reads from the exit status and stdout:

* ``incident-owned`` (exit 0): the observer owns this run, so the workflow takes
  no rerun, classification or revert action in this pass.
* ``ordinary`` (exit 0): the existing reconciler policy runs unchanged. This is
  also the answer when no observer is configured for the repository.
* no readable answer from a configured observer (exit 1, nothing on stdout): the
  cause is named on stderr and the workflow's ``set -e`` stops the pass before
  any action, because guessing "ordinary" could race the observer's revert.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from urllib.parse import urlsplit

from livespec_dev_tooling.incident_ci_authority import CiAuthorityBoundary

__all__: list[str] = ["main"]

_URL_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_URL"
_TOKEN_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"  # noqa: S105 — a variable name.


def main(*, argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Print the owner of one exact failed run, or exit 1 naming why it is unknown."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--repository", required=True)
    _ = parser.add_argument("--head-sha", required=True)
    _ = parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args(argv)
    env = os.environ if environ is None else environ
    url = env.get(_URL_VARIABLE, "")
    if not url:
        return _print(
            status="ordinary", reason="no incident observer is configured for this repository"
        )
    result = CiAuthorityBoundary(
        observer_url=url, observer_token=env.get(_TOKEN_VARIABLE, "")
    ).ordinary_action(
        query={"repository": args.repository, "head_sha": args.head_sha, "run_id": args.run_id}
    )
    if result is None:
        _ = sys.stderr.write(
            "master-health: the incident observer at "
            + (urlsplit(url).hostname or "an unparseable URL")
            + " gave no readable ownership answer for run "
            + str(args.run_id)
            + "; no rerun, classification or revert action is taken in this pass\n"
        )
        return 1
    return _print(status=result.status, reason=result.reason)


def _print(*, status: str, reason: str) -> int:
    _ = sys.stdout.write(json.dumps({"status": status, "reason": reason}, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
