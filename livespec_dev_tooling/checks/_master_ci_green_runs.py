"""Which `ci-green` check runs on master's head commit are master's own verdict.

A private helper of `master_ci_green` (livespec-dev-tooling-7w757z, review F1
on livespec-dev-tooling#3965). The check-runs endpoint is keyed on the COMMIT,
not the branch, and each workflow run is its own check suite. A push to an
`incident-scratch/**` branch runs the full CI workflow, and a drill creates
that branch at master's head, so one commit can carry a `ci-green` from
master's push run and another from the scratch run. Only the first is
master-health evidence.

These are the pure halves of that selection: the address of master's own push
runs of a commit, the check suites those runs own, and the check runs that
belong to one of those suites. The `gh` reads and their failure handling stay
in `master_ci_green`, beside the check-runs read they mirror.
"""

from __future__ import annotations

from typing import cast

__all__: list[str] = [
    "from_master_push_runs",
    "master_push_runs_endpoint",
    "master_push_suite_ids",
]

_MASTER_REF = "master"
# The only workflow-run event whose runs speak for master's health: a push to
# master. A pull_request run, or a push run of another branch on the same
# commit, is never master-health evidence.
_MASTER_PUSH_EVENT = "push"


def master_push_runs_endpoint(*, repository: str, head_sha: str) -> str:
    """The address of master's own push runs of `head_sha`, across every workflow.

    Every workflow rather than one named file, so the selection stays correct
    in a governed repository whose gating workflow has a different filename.
    """
    return (
        f"repos/{repository}/actions/runs"
        f"?branch={_MASTER_REF}&event={_MASTER_PUSH_EVENT}&head_sha={head_sha}&per_page=100"
    )


def master_push_suite_ids(*, payload: object) -> frozenset[int] | None:
    """The check suites of the master push runs a workflow-runs answer lists.

    None when the answer is not a JSON object at all. The endpoint already
    filters on branch and event; both are re-checked on every run anyway, so
    an answer that ever included another branch's run could still not lend it
    master's authority.
    """
    if not isinstance(payload, dict):
        return None
    runs = cast("dict[str, object]", payload).get("workflow_runs")
    if not isinstance(runs, list):
        return frozenset()
    suite_ids: set[int] = set()
    for entry in cast("list[object]", runs):
        if not isinstance(entry, dict):
            continue
        run = cast("dict[str, object]", entry)
        suite_id = run.get("check_suite_id")
        if (
            run.get("head_branch") == _MASTER_REF
            and run.get("event") == _MASTER_PUSH_EVENT
            and isinstance(suite_id, int)
        ):
            suite_ids.add(suite_id)
    return frozenset(suite_ids)


def _check_suite_id(*, entry: object) -> int | None:
    """The check-suite id of one check-run record, or None when it carries none."""
    if not isinstance(entry, dict):
        return None
    suite = cast("dict[str, object]", entry).get("check_suite")
    if not isinstance(suite, dict):
        return None
    suite_id = cast("dict[str, object]", suite).get("id")
    return suite_id if isinstance(suite_id, int) else None


def from_master_push_runs(*, entries: list[object], suite_ids: frozenset[int]) -> list[object]:
    """The check-run records, in the API's order, whose check suite is a master push run's."""
    return [entry for entry in entries if _check_suite_id(entry=entry) in suite_ids]
