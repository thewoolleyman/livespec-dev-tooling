"""Reconcile a repo's ONE `release-lane-red` issue against its watched lanes.

The I/O half of the release-lane issue producer, paired with the pure transition
table in `livespec_dev_tooling/cross_repo/release_lane_issue.py`. Invoked as
`python -m livespec_dev_tooling.cross_repo.release_lane_issue_runner
<workflow-file> [...]` with the SAME caller-supplied watched set the sibling
`release_lane_watch_runner` takes — this one loops it in a single process rather
than being invoked once per lane, because the issue it writes is per REPO and a
per-lane invocation could only ever see one lane's share of the truth.

IT REUSES THE DETECTOR AND ITS FETCHER RATHER THAN RESTATING THEM. `fetch_runs`,
`lane_state` and `notice_text` are imported, not reimplemented: the three
properties the detector earned (state not edges, the absolute last-green, and
knowing when its own input is truncated) are exactly what a second copy would
quietly lose, and the notice line is also what a reader of the issue sees.

IT TALKS TO THE REST API THROUGH THE STDLIB, NOT THROUGH `gh`. Same reason as
the sibling: `gh` is not installed on the self-hosted runner, where the first
version of the watcher died with FileNotFoundError. Diagnostics flow through
structlog to stderr — `print` is banned here by T20 and direct writes by
`check-no-write-direct`.

EXIT CODES ARE THE SIBLING'S THREE-VALUED CONTRACT, WORST-ACROSS-THE-SET:
    0  every watched lane is healthy (or failing below the transient threshold)
    1  at least one lane is FAILING — this is the finding
    2  at least one lane CANNOT BE MEASURED, or the issue could not be
       reconciled — the forge was unreachable, unauthorized, or unparsable
So the job status still reflects lane health even though the durable signal is
now the issue. A failed reconcile escalates to 2 rather than passing quietly:
the screen reads the ISSUE, so a write that did not land leaves a reader looking
at a stale row with nothing to tell them it is stale.

WHAT IS NOT HERE. The `issues: write` permission and the workflow step that
invokes this module are a separate maintainer-authorized workflow change; this
module ships ready for it and touches no workflow file itself.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.cross_repo.release_lane_issue import (  # noqa: E402
    ACTION_NOOP,
    ACTION_OPEN,
    ACTION_UPDATE,
    ISSUE_LABEL,
    ISSUE_TITLE,
    IssueAction,
    issue_action,
)
from livespec_dev_tooling.cross_repo.release_lane_watch import (  # noqa: E402
    lane_state,
    notice_text,
)
from livespec_dev_tooling.cross_repo.release_lane_watch_runner import (  # noqa: E402
    fetch_runs,
)

__all__: list[str] = ["apply_action", "find_open_issue", "main"]

_API = "https://api.github.com"
_TIMEOUT_S = 30

_HEALTHY = 0
_FAILING = 1
_CANNOT_MEASURE = 2

_UNMEASURED = "CANNOT MEASURE — forge unreachable, unauthorized, or unparsable"


def _request_json(
    *, url: str, token: str, method: str, payload: dict[str, object] | None
) -> object | None:
    """Call the REST API and return the decoded body, or None if it did not land.

    `None` is the DID-NOT-LAND track and is never conflated with an empty
    answer: a reconcile that could not reach the forge must not read as a
    reconcile that found nothing to do.
    """
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)  # noqa: S310
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("Authorization", f"Bearer {token}")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_S) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def find_open_issue(*, slug: str, token: str) -> tuple[bool, int | None]:
    """Return whether the issue state was MEASURED, and the open issue if any.

    The two halves of the answer are separate on purpose. `(False, None)` — the
    forge could not be read — must never be acted on: it is indistinguishable
    in shape from `(True, None)` ("there is no open issue"), and treating the
    first as the second is exactly how a watcher opens a duplicate issue on
    every blip.

    The `/issues` collection endpoint returns PULL REQUESTS alongside issues,
    distinguished only by a `pull_request` key, so a labelled PR would
    otherwise be picked up and patched as if it were the signal. When more than
    one issue somehow carries the label, the LOWEST number wins: the durable
    one is the oldest, and a deterministic choice keeps successive runs from
    ping-ponging between two rows.
    """
    parsed = _request_json(
        url=f"{_API}/repos/{slug}/issues?labels={ISSUE_LABEL}&state=open&per_page=100",
        token=token,
        method="GET",
        payload=None,
    )
    if not isinstance(parsed, list):
        return (False, None)
    numbers: list[int] = []
    for row in cast("list[object]", parsed):
        if not isinstance(row, dict):
            continue
        record = cast("Mapping[str, object]", row)
        if "pull_request" in record:
            continue
        number = record.get("number")
        if isinstance(number, int):
            numbers.append(number)
    return (True, min(numbers) if numbers else None)


def apply_action(*, slug: str, token: str, action: IssueAction) -> bool:
    """Carry the decided transition to the forge; False when the write did not land.

    An UPDATE patches the body unconditionally rather than diffing it first.
    That is deliberate: the patch also refreshes the issue's `updated_at`, which
    is what lets a reader tell "still red as of this morning" from "red once,
    months ago" without opening a single run.
    """
    if action.kind == ACTION_NOOP:
        return True
    if action.kind == ACTION_OPEN:
        opened = _request_json(
            url=f"{_API}/repos/{slug}/issues",
            token=token,
            method="POST",
            payload={"title": ISSUE_TITLE, "body": action.body, "labels": [ISSUE_LABEL]},
        )
        return opened is not None
    payload: dict[str, object] = (
        {"body": action.body} if action.kind == ACTION_UPDATE else {"state": "closed"}
    )
    patched = _request_json(
        url=f"{_API}/repos/{slug}/issues/{action.issue_number}",
        token=token,
        method="PATCH",
        payload=payload,
    )
    return patched is not None


def _survey(
    *, slug: str, token: str, workflows: list[str], log: structlog.stdlib.BoundLogger
) -> tuple[int, list[str]]:
    """Measure every watched lane, returning the worst exit code and the red notices.

    A lane that cannot be measured contributes a NOTICE as well as the exit
    code, which is what keeps it out of the recovered state downstream.

    `fetch_runs` rides `IOResult`, and the failure it names is LOGGED with its
    detail — which of the three unmeasurable conditions fired — beside the
    sentence naming all three. The NOTICE deliberately keeps that sentence
    alone: it is issue-body text, and widening what a reader of the issue sees
    is a separate decision from putting the fetch on the railway.
    """
    worst = _HEALTHY
    notices: list[str] = []
    for workflow in workflows:
        fetched = fetch_runs(slug=slug, workflow=workflow, token=token)
        if isinstance(fetched, IOFailure):
            unmeasurable = unsafe_perform_io(fetched.failure())
            log.error(_UNMEASURED, workflow=workflow, repository=slug, detail=unmeasurable.detail)
            notices.append(f"{workflow}: {_UNMEASURED}")
            worst = max(worst, _CANNOT_MEASURE)
            continue
        state = lane_state(runs=unsafe_perform_io(fetched.unwrap()))
        text = notice_text(workflow=workflow, state=state)
        if not text:
            log.info("release lane healthy", workflow=workflow, repository=slug)
            continue
        log.error("release lane FAILING", workflow=workflow, repository=slug, notice=text)
        notices.append(text)
        worst = max(worst, _FAILING)
    return (worst, notices)


def _configure_logging() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("release_lane_issue")


def main() -> int:
    """Watch the argv-named lane set and reconcile the repo's one issue against it."""
    log = _configure_logging()
    workflows = [arg for arg in sys.argv[1:] if arg]
    slug = os.environ.get("GITHUB_REPOSITORY") or ""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not workflows or not slug or not token:
        log.error(
            "CANNOT MEASURE — the watcher was not given what it needs to ask the forge",
            have_workflows=bool(workflows),
            have_repository_slug=bool(slug),
            have_token=bool(token),
        )
        return _CANNOT_MEASURE

    worst, notices = _survey(slug=slug, token=token, workflows=workflows, log=log)
    measured, open_issue_number = find_open_issue(slug=slug, token=token)
    if not measured:
        log.error(
            "CANNOT MEASURE — the release-lane-red issue could not be read; wrote nothing",
            repository=slug,
        )
        return max(worst, _CANNOT_MEASURE)

    action = issue_action(red_notices=notices, open_issue_number=open_issue_number)
    if not apply_action(slug=slug, token=token, action=action):
        log.error(
            "CANNOT MEASURE — the release-lane-red issue write did not land",
            repository=slug,
            action=action.kind,
            issue_number=action.issue_number,
        )
        return max(worst, _CANNOT_MEASURE)
    log.info(
        "release-lane-red issue reconciled",
        repository=slug,
        action=action.kind,
        issue_number=action.issue_number,
        red_lanes=len(notices),
    )
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
