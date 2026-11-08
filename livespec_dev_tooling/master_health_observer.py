"""Ask the protected incident observer who owns one failed master action.

The master-health decision modules deliberately remain network-free.  This is
their workflow-side transport: it emits an exact ownership answer for the
workflow to fence before it invokes the pure policy or performs that policy's
step.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from livespec_dev_tooling.incident_ci_authority import CiAuthorityBoundary

__all__: list[str] = ["main"]


def main(argv: list[str] | None = None) -> int:
    """Print the owner of an exact failed run, or fail closed."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--repository", required=True)
    _ = parser.add_argument("--head-sha", required=True)
    _ = parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args(argv)
    result = CiAuthorityBoundary(
        observer_url=os.environ.get("LIVESPEC_INCIDENT_OBSERVER_URL", ""),
        observer_token=os.environ.get("LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN", ""),
    ).ordinary_action(
        query={"repository": args.repository, "head_sha": args.head_sha, "run_id": args.run_id}
    )
    if result is None:
        return 1
    _ = sys.stdout.write(
        json.dumps({"status": result.status, "reason": result.reason}, sort_keys=True) + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
