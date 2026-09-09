"""Report whether a release workflow's lane is persistently failing.

The caller half of the release-lane watcher, lifted from `livespec-overseer`'s
`scripts/release-lane-watch.py` (its work-item `overseer-hgq4wi.15`) alongside
the pure detector in `livespec_dev_tooling/cross_repo/release_lane_watch.py`.
Invoked as `python -m livespec_dev_tooling.cross_repo.release_lane_watch_runner
<workflow-file>` by `reusable-release-lane-watch.yml`, once per workflow file in
the CALLER-SUPPLIED watched set.

The forge query lives HERE, in the caller, never in the enforcement aggregate:
`just check` runs on every commit and push, and a network dependency inside it
would make the gate fail for reasons unrelated to the tree.

IT TALKS TO THE REST API THROUGH THE STDLIB, NOT THROUGH `gh`. The first version
shelled out to `gh run list` and died with FileNotFoundError on the self-hosted
runner, where `gh` is not installed — the watcher for a lane nobody was watching
could not itself run. urllib is always present, which is the same stdlib-only
posture the rest of this package holds.

IT USES THE WORKFLOW-SCOPED RUNS ENDPOINT
(`/repos/{slug}/actions/workflows/{workflow}/runs`). The unscoped
`/repos/{slug}/actions/runs` form silently IGNORES a workflow identifier and
returns every workflow's runs, which reads as a healthy lane whenever any other
workflow is green.

EXIT CODES ARE THREE-VALUED ON PURPOSE:
    0  the lane is healthy (or failing below the transient threshold)
    1  the lane is FAILING — this is the finding
    2  CANNOT MEASURE — the forge was unreachable, unauthorized, or unparsable
A watcher that cannot measure must never report healthy. Collapsing 2 into 0
would make an unreachable forge look like a green lane, which is the vacuous-pass
defect this watcher exists to remove; collapsing it into 1 would cry wolf and get
the job muted. So the caller can tell all three apart — and the calling workflow
renders `::error::` for 1 and `::warning::` for 2 from the exit code, because a
GitHub Actions annotation is a presentation concern of the venue, not of this
module (`print` is banned here by T20 and direct writes by
`check-no-write-direct`; diagnostics flow through structlog to stderr, the same
output discipline every module in this package holds).

THE EXIT CODE IS THE VENUE'S CONTRACT; IT IS NOT THIS MODULE'S ERROR CHANNEL.
Inside the module the CANNOT-MEASURE track is `IOResult`'s failure track, and
`main` is the one place the three-way collapse onto `2` happens. That separation
is what lets the operator read WHICH of the three conditions fired without
widening the exit contract the reusable workflow renders annotations from.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.cross_repo.release_lane_watch import (  # noqa: E402
    lane_state,
    notice_text,
)

__all__: list[str] = ["LaneUnmeasurable", "fetch_runs", "main"]

# Deliberately far wider than any observed block. The real 123-cut outage reads
# as 4 cuts at limit 20 and 84 at limit 100 -- a limit is a measurement boundary,
# so this asks for far more history than it expects to need and lets the detector
# report truncation if even that is not enough.
_PER_PAGE = 100
_PAGES = 4
_TIMEOUT_S = 30

_HEALTHY = 0
_FAILING = 1
_CANNOT_MEASURE = 2


@dataclass(frozen=True, kw_only=True)
class LaneUnmeasurable:
    """This run did not obtain `workflow`'s history from `slug`, and why not.

    ONE inhabitant rather than three, for the same reason
    `_settle_window.LatestReleaseUnreadable` has one: all three conditions call
    for the SAME response — do not report healthy, do not report a finding, exit
    CANNOT MEASURE. `detail` distinguishes them for the human without inventing
    a discriminated union no consumer branches on.

    `detail` names the PAGE as well as the condition. A full first page followed
    by a dead second is a different fact from a lane that never answered at all:
    the first says the forge was reachable and the window is merely short, the
    second says nothing was measured. Reading them as one sentence is exactly
    the flattening this type replaces.
    """

    slug: str
    workflow: str
    detail: str


def fetch_runs(
    *, slug: str, workflow: str, token: str
) -> IOResult[list[dict[str, str]], LaneUnmeasurable]:
    """The lane's decided runs, or the reason this run could not measure the lane.

    The failure track IS the CANNOT-MEASURE track, and it is never conflated
    with an empty history: an unreachable, unauthorized, or unparsable forge
    must not read as a lane with no failures in it. The converse holds too and
    is the reason the success track keeps EVERY answer it managed to obtain —
    an answer is an answer however it reads, so a lane the forge measured as
    having no runs at all is `IOSuccess([])`, not a failure.

    The three conditions the replaced `None` covered, now told apart:

    - the page did not answer readably — a dead socket, a timeout, or bytes
      that are not JSON. `detail` carries the exception TYPE, which is what
      separates an outage (`URLError`) from an HTML error page served with a
      200 (`JSONDecodeError`); both reach this one clause.
    - the page parsed and is NOT an object. The runs endpoint exists SOLELY to
      answer with one, so a JSON array or scalar there is a non-answer.
    - the page is an object carrying no `workflow_runs` list. A `Not Found`
      body parses cleanly and has no history in it — reporting that as an
      empty lane would be the vacuous pass this watcher exists to remove.
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
                parsed: object = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError, OSError) as unanswered:
            return _unmeasurable(
                slug=slug,
                workflow=workflow,
                detail=(
                    f"page {page} did not answer readably — "
                    f"{type(unanswered).__name__}: {unanswered}"
                ),
            )
        # The two narrowings below are the typed parse boundary: `json.loads`
        # yields `Any`, and a forge that answered with something OTHER than an
        # object carrying a run list has not measured the lane — that is the
        # CANNOT-MEASURE track, never an empty history.
        if not isinstance(parsed, dict):
            return _unmeasurable(
                slug=slug,
                workflow=workflow,
                detail=f"page {page} answered with a {type(parsed).__name__}, not a runs object",
            )
        payload = cast("Mapping[str, object]", parsed)
        runs = payload.get("workflow_runs")
        if not isinstance(runs, list):
            return _unmeasurable(
                slug=slug,
                workflow=workflow,
                detail=f"page {page} carries no `workflow_runs` list",
            )
        page_runs = cast("list[Mapping[str, object]]", runs)
        collected.extend(
            {
                "conclusion": str(r.get("conclusion") or ""),
                "created_at": str(r.get("created_at") or ""),
            }
            for r in page_runs
        )
        if len(page_runs) < _PER_PAGE:
            break
    return IOSuccess(collected)


def _unmeasurable(
    *, slug: str, workflow: str, detail: str
) -> IOResult[list[dict[str, str]], LaneUnmeasurable]:
    """The failure track, built once so the three conditions cannot drift apart.

    The lane identity is the same at all three sites and only `detail` differs;
    repeating `slug=` and `workflow=` three times is how one of them ends up
    naming a different lane than the request that failed.
    """
    return IOFailure(LaneUnmeasurable(slug=slug, workflow=workflow, detail=detail))


def main() -> int:
    """Watch ONE lane, named by argv, and report its state as an exit code."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("release_lane_watch")
    workflow = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = os.environ.get("GITHUB_REPOSITORY") or ""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not workflow or not slug or not token:
        log.error(
            "CANNOT MEASURE — the watcher was not given what it needs to ask the forge",
            workflow=workflow,
            have_workflow=bool(workflow),
            have_repository_slug=bool(slug),
            have_token=bool(token),
        )
        return _CANNOT_MEASURE

    fetched = fetch_runs(slug=slug, workflow=workflow, token=token)
    if isinstance(fetched, IOFailure):
        # The sentence is unchanged because it is what the operator greps for;
        # `detail` is what tells them which of its three clauses actually fired.
        unmeasurable = unsafe_perform_io(fetched.failure())
        log.error(
            "CANNOT MEASURE — forge unreachable, unauthorized, or unparsable",
            workflow=workflow,
            repository=slug,
            detail=unmeasurable.detail,
        )
        return _CANNOT_MEASURE
    runs = unsafe_perform_io(fetched.unwrap())

    state = lane_state(runs=runs)
    text = notice_text(workflow=workflow, state=state)
    if not text:
        log.info(
            "release lane healthy",
            workflow=workflow,
            repository=slug,
            runs_considered=state["runs_considered"],
            last_green=state["last_green"],
        )
        return _HEALTHY
    log.error(
        "release lane FAILING",
        workflow=workflow,
        repository=slug,
        notice=text,
        consecutive_failures=state["consecutive_failures"],
        failing_since=state["failing_since"],
        last_green=state["last_green"],
        truncated=state["truncated"],
    )
    return _FAILING


if __name__ == "__main__":
    raise SystemExit(main())
