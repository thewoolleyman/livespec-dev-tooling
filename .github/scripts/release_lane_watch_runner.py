#!/usr/bin/env python3
"""Report whether ONE release workflow's lane is persistently failing.

The forge query lives HERE, in the caller, never in the enforcement aggregate:
`just check` runs on every commit and push, and a network dependency inside it
would make the gate fail for reasons unrelated to the tree.

IT TALKS TO THE REST API THROUGH THE STDLIB, NOT THROUGH `gh`. The overseer's
first version shelled out to `gh run list` and died with FileNotFoundError on a
self-hosted runner where `gh` is not installed — the watcher for a lane nobody
was watching could not itself run. urllib is always present.

It uses the WORKFLOW-SCOPED runs endpoint. The unscoped
`actions/runs?workflow_id=<id>` form SILENTLY IGNORES the workflow id and
returns the repo's most recent run for EVERY workflow, which reads as a healthy
lane whatever the lane is actually doing.

EXIT CODES ARE THREE-VALUED ON PURPOSE:
    0  the lane is healthy (or failing below the transient threshold)
    1  the lane is FAILING — this is the finding
    2  CANNOT MEASURE — the forge was unreachable, unauthorized, or unparsable
A watcher that cannot measure must never report healthy. Collapsing 2 into 0
would make an unreachable forge look like a green lane; collapsing it into 1
would cry wolf and get the job muted. The CALLING WORKFLOW renders the operator
annotation from the exit code — this module emits structured diagnostics only,
because `print` is banned in this tree and an Actions annotation is a
presentation concern belonging to the workflow step.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_REPO_ROOT))

_VENDOR_DIR = _REPO_ROOT / "livespec_dev_tooling" / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402 — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.cross_repo.release_lane_watch import (  # noqa: E402
    lane_state,
    notice_text,
)

__all__: list[str] = []

_PER_PAGE = 100
_PAGES = 4
_TIMEOUT_S = 30
_DEFAULT_MIN_CONSECUTIVE = 2
_EXIT_HEALTHY = 0
_EXIT_FAILING = 1
_EXIT_CANNOT_MEASURE = 2


def fetch_runs(*, slug: str, workflow: str, token: str) -> list[dict[str, str]] | None:
    """Return decided runs, or `None` when the lane cannot be measured.

    Deliberately asks for far more history than it expects to need: the real
    123-cut outage read as 4 cuts at limit 20 and 84 at limit 100, so a narrow
    window turns a sixteen-day outage into a rounding error.
    """
    collected: list[dict[str, str]] = []
    for page in range(1, _PAGES + 1):
        url = (
            f"https://api.github.com/repos/{slug}/actions/workflows/{workflow}"
            f"/runs?per_page={_PER_PAGE}&page={page}"
        )
        request = urllib.request.Request(url)  # noqa: S310
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:  # noqa: S310
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            return None
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            return None
        collected.extend(
            {
                "conclusion": str(run.get("conclusion") or ""),
                "created_at": str(run.get("created_at") or ""),
            }
            for run in runs
        )
        if len(runs) < _PER_PAGE:
            break
    return collected


def main() -> int:
    """Measure the one lane named in argv and return its three-valued verdict."""
    emit = structlog.get_logger("release_lane_watch")
    workflow = sys.argv[1]
    slug = os.environ["REPO"]
    token = os.environ["GH_TOKEN"]
    min_consecutive = int(os.environ.get("MIN_CONSECUTIVE") or _DEFAULT_MIN_CONSECUTIVE)

    runs = fetch_runs(slug=slug, workflow=workflow, token=token)
    if runs is None:
        emit.error(
            "release lane could not be measured — this is NOT a healthy verdict",
            workflow=workflow,
            repo=slug,
        )
        return _EXIT_CANNOT_MEASURE

    state = lane_state(runs=runs)
    notice = notice_text(workflow=workflow, state=state, min_consecutive=min_consecutive)
    if notice:
        emit.error("release lane is persistently failing", workflow=workflow, notice=notice)
        return _EXIT_FAILING
    emit.info(
        "release lane healthy",
        workflow=workflow,
        runs_considered=state["runs_considered"],
    )
    return _EXIT_HEALTHY


if __name__ == "__main__":
    sys.exit(main())
