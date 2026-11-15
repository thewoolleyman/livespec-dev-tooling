"""Ask the incident observer who owns the master-health reconciler's next step.

The ``cross_repo/master_health_*`` decision modules stay network-free, and a
test enforces that. This module is their workflow-side transport. The reusable
reconciler workflow runs it after the decision and immediately before the one
step it would perform, so the answer is read seconds before any side effect
rather than before the whole gather.

What it asks about is the whole pass, not one run: every commit from the
branch head back to the newest green commit, plus the commit of the run the
step would rerun and the culprit it would revert. An incident commit anywhere
in that window makes the step incident-owned.

The outcomes, which the workflow reads from the exit status and stdout:

* ``incident-owned`` (exit 0): rerun, classification and revert are left to
  the observer, and the workflow takes no action in this pass.
* ``ordinary`` (exit 0): the existing reconciler policy runs unchanged. The
  answer carries the observer's receipt for the one step it lets run. A
  repository with no observer, and a step that takes no action, also answer
  ``ordinary`` without asking.
* no readable answer in a repository that has an observer (exit 1, nothing on
  stdout): the cause is named on stderr and the workflow stops before any
  action, because guessing ``ordinary`` could race the observer's revert.

Whether a repository has an observer is COMMITTED configuration,
``OBSERVED_REPOSITORIES``, and not only the presence of a runtime variable: a
variable that is not mapped through, or that a typo empties, reads as the empty
string, and inferring "no observer" from it would fail open.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from livespec_dev_tooling.cross_repo.master_health_reconcile import STEP_NONE
from livespec_dev_tooling.cross_repo.master_health_state import CI_FAILURE, CI_SUCCESS
from livespec_dev_tooling.incident_ci_authority import UNREADABLE, CiAuthorityBoundary

__all__: list[str] = [
    "HOSTED_REACHABILITY_PROOFS",
    "OBSERVED_REPOSITORIES",
    "main",
    "ownership_window",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
# Every repository an independent incident observer watches. It is kept equal to
# the observer role's `incident_observer_repository` by a test, so installing an
# observer for a repository and fencing its reconciler are one committed change.
OBSERVED_REPOSITORIES = frozenset({"thewoolleyman/livespec-dev-tooling"})
# The committed opt-in that admits ARMING the reconciler in an observed
# repository: the URL of a GitHub-hosted Actions run that reached the observer's
# POST /ordinary-action. The reconciler must stay on hosted runners, and the
# observer is tailnet-only, so until such a run exists every acting pass there
# would fail closed. wire-fleet-member therefore refuses to install the shim
# into a repository in OBSERVED_REPOSITORIES with no entry here: adoption first,
# then arming (review finding F5 on livespec-dev-tooling#3915).
# livespec-dev-tooling's run (livespec-dev-tooling-jpfdcx, 2026-11-10) ran on a
# GitHub-hosted runner, cloned released v1.193.0, asked POST /ordinary-action
# through the observer's public Funnel with the reconciler's own client and env,
# and got HTTP 202 and the exact ownership answer; a no-token POST got 403.
HOSTED_REACHABILITY_PROOFS: dict[str, str] = {
    "thewoolleyman/livespec-dev-tooling": (
        "https://github.com/thewoolleyman/livespec-dev-tooling/actions/runs/42922861122"
    ),
}
_URL_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_URL"
_TOKEN_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"  # noqa: S105 — a variable name.
_SHA = re.compile(r"[0-9a-f]{40}")
_NO_ACTION = "; no rerun, classification or revert action is taken in this pass\n"


def ownership_window(
    *, state: dict[str, object], runs: list[object], step: dict[str, object]
) -> frozenset[str] | None:
    """Every commit this reconciler pass can touch, or None when the recording is malformed.

    The walk follows ``parent_sha`` from the head while each commit is not green,
    so it covers the red episode and any pending commits above or inside it. The
    head is included unless it is recorded green. The commit of the run the step
    would rerun is added by the workflow's own rule (the first failed gating run
    in ``runs``), and so is the culprit an ``open-revert`` step names.
    """
    head = state.get("head_sha")
    commits = state.get("commits")
    if not isinstance(head, str) or not isinstance(commits, list):
        return None
    by_sha: dict[str, dict[str, object]] = {}
    for commit in cast("list[object]", commits):
        if not isinstance(commit, dict):
            return None
        record = cast("dict[str, object]", commit)
        by_sha[str(record.get("sha"))] = record
    window: set[str] = set()
    cursor = by_sha.get(head)
    if cursor is None:
        window.add(head)
    while cursor is not None and cursor.get("ci_conclusion") != CI_SUCCESS:
        sha = str(cursor.get("sha"))
        if sha in window:
            break
        window.add(sha)
        cursor = by_sha.get(str(cursor.get("parent_sha")))
    failed = [
        cast("dict[str, object]", run)
        for run in runs
        if isinstance(run, dict) and cast("dict[str, object]", run).get("conclusion") == CI_FAILURE
    ]
    if failed:
        window.add(str(failed[0].get("head_sha")))
    culprit = step.get("culprit_sha")
    if isinstance(culprit, str):
        window.add(culprit)
    if not all(_SHA.fullmatch(sha) for sha in window):
        return None
    return frozenset(window)


def main(*, argv: list[str] | None = None, environ: Mapping[str, str] | None = None) -> int:
    """Print who owns the reconciler's next step, or exit 1 naming why it is unknown."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--repository", required=True)
    _ = parser.add_argument("--state", type=Path, required=True)
    _ = parser.add_argument("--runs", type=Path, required=True)
    _ = parser.add_argument("--step", type=Path, required=True)
    args = parser.parse_args(argv)
    raw_step = _read(path=cast("Path", args.step))
    step = cast("dict[str, object]", raw_step) if isinstance(raw_step, dict) else {}
    if not isinstance(step.get("kind"), str):
        return _fail(cause="the decided step " + str(args.step) + " is unreadable or malformed")
    env = os.environ if environ is None else environ
    return _answer(
        repository=cast("str", args.repository),
        step=step,
        url=env.get(_URL_VARIABLE, ""),
        token=env.get(_TOKEN_VARIABLE, ""),
        state=_read(path=cast("Path", args.state)),
        runs=_read(path=cast("Path", args.runs)),
    )


def _answer(
    *,
    repository: str,
    step: dict[str, object],
    url: str,
    token: str,
    state: object,
    runs: object,
) -> int:
    """Ask the observer when this step acts in a repository that has one."""
    kind = cast("str", step["kind"])
    if kind == STEP_NONE:
        return _print(status="ordinary", reason="the step takes no action; ownership not asked")
    if repository not in OBSERVED_REPOSITORIES and not url:
        return _print(
            status="ordinary", reason="no incident observer is configured for this repository"
        )
    if not url:
        return _fail(
            cause="committed configuration says "
            + repository
            + " has an incident observer, but "
            + _URL_VARIABLE
            + " is empty in this run"
        )
    window = (
        ownership_window(
            state=cast("dict[str, object]", state),
            runs=cast("list[object]", runs),
            step=step,
        )
        if isinstance(state, dict) and isinstance(runs, list)
        else None
    )
    if window is None:
        return _fail(cause="the recorded state or gating runs are unreadable or malformed")
    answer = CiAuthorityBoundary(observer_url=url, observer_token=token).ordinary_action(
        query={"repository": repository, "action": kind, "window_shas": sorted(window)}
    )
    if answer.status == UNREADABLE:
        return _fail(
            cause="the incident observer gave no readable ownership answer: " + answer.reason
        )
    return _print(status=answer.status, reason=answer.reason, receipt=answer.receipt)


def _read(*, path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _print(*, status: str, reason: str, receipt: str | None = None) -> int:
    _ = sys.stdout.write(
        json.dumps({"status": status, "reason": reason, "receipt": receipt}, sort_keys=True) + "\n"
    )
    return 0


def _fail(*, cause: str) -> int:
    _ = sys.stderr.write("master-health: " + cause + _NO_ACTION)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
