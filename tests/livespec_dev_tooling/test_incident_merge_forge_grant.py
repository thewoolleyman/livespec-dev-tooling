"""The principal's gating reads fit the merge App's grant, and the queue exclusion survives.

Work-item livespec-dev-tooling-o6u7jm. The incident-merge App holds Contents read, Pull
requests read and write, Checks read, Commit statuses read and Metadata read, and nothing
wider. Measured live with the App's own token (2026-11-18): the classic branch-protection
read answers 403 (it needs Administration read) and the Actions runs read needs Actions read
(it answers only for a public repository). So the verdict reads the effective required set
from the repository's RULESETS alone, and tells a merge-queue run apart by its check suite's
head branch, never by an Actions run's event.
"""

from __future__ import annotations

import json

import pytest

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.incident_merge_forge import (
    ForgeReader,
    Green,
    NotGreen,
    OffendingCheck,
    required_checks_verdict,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-o6u7jm

_REPO = "o/r"
_HEAD = "h" * 40
_SUITES = f"repos/{_REPO}/commits/{_HEAD}/check-suites?per_page=100"
_RUNS = f"repos/{_REPO}/commits/{_HEAD}/check-runs?per_page=100"
_STATUS = f"repos/{_REPO}/commits/{_HEAD}/status?per_page=100"
_RULES = f"repos/{_REPO}/rules/branches/master?per_page=100"
_CLASSIC = f"repos/{_REPO}/branches/master/protection/required_status_checks"
_GRANTED = {f"repos/{_REPO}", _RULES, _SUITES, _RUNS, _STATUS}
_QUEUE_BRANCH = "gh-readonly-queue/master/pr-9-abcdef"
_PR_BRANCH = "incident/inc-1-attempt-1"


def _ok(*, body: object) -> GhRead:
    return GhRead(returncode=0, stdout=json.dumps(body), stderr="")


def _run(*, name: str, run_id: int, suite: int) -> dict[str, object]:
    return {
        "id": run_id,
        "name": name,
        "head_sha": _HEAD,
        "status": "completed",
        "conclusion": "success",
        "check_suite": {"id": suite},
    }


def _world(*, runs: list[dict[str, object]], suites: list[dict[str, object]]) -> dict[str, GhRead]:
    contexts = [{"context": "ci-green"}, {"context": "lint"}]
    rule = {
        "type": "required_status_checks",
        "ruleset_id": 9,
        "parameters": {"required_status_checks": contexts},
    }
    return {
        f"repos/{_REPO}": _ok(body={"default_branch": "master"}),
        _RULES: _ok(body=[[rule]]),
        _SUITES: _ok(body=[{"check_suites": suites}]),
        _RUNS: _ok(body=[{"check_runs": runs}]),
        _STATUS: _ok(body=[{"statuses": []}]),
        _CLASSIC: _ok(body={"contexts": ["classic-only"], "strict": False}),
    }


def _green_world() -> dict[str, GhRead]:
    return _world(
        runs=[_run(name="ci-green", run_id=1, suite=1), _run(name="lint", run_id=2, suite=1)],
        suites=[{"id": 1, "head_branch": _PR_BRANCH}, {"id": 2, "head_branch": _QUEUE_BRANCH}],
    )


def _verdict(*, world: dict[str, GhRead]) -> tuple[Green | NotGreen, list[str]]:
    reads: list[str] = []

    def read(*, args: list[str]) -> GhRead:
        reads.append(args[-1])
        return world.get(args[-1], GhRead(returncode=1, stdout="", stderr="HTTP 404: not held"))

    forge: ForgeReader = read
    return required_checks_verdict(forge=forge, repo=_REPO, head_sha=_HEAD), reads


def test_the_verdict_reads_only_endpoints_inside_the_apps_grant():
    verdict, reads = _verdict(world=_green_world())
    facts = [
        verdict == Green(head_sha=_HEAD, contexts=frozenset({"ci-green", "lint"})),
        set(reads) <= _GRANTED,
        not any("protection" in path or "actions/runs" in path for path in reads),
        _SUITES in reads,
    ]
    assert all(facts)


def test_classic_protection_contexts_are_not_read_so_they_are_not_required():
    verdict, reads = _verdict(world=_green_world())
    assert all([isinstance(verdict, Green), _CLASSIC not in reads])


@pytest.mark.parametrize(
    ("suites", "expected"),
    [
        ([{"id": 1, "head_branch": _QUEUE_BRANCH}], "merge-group-only"),
        ([{"id": 1, "head_branch": None}], "event-unknown"),
        ([{"id": 5, "head_branch": _PR_BRANCH}], "event-unknown"),
    ],
)
def test_a_run_in_a_merge_queue_or_unidentified_suite_never_counts(suites, expected):
    world = _world(
        runs=[_run(name="ci-green", run_id=1, suite=1), _run(name="lint", run_id=2, suite=7)],
        suites=[*suites, {"id": 7, "head_branch": _PR_BRANCH}],
    )
    verdict, _ = _verdict(world=world)
    assert isinstance(verdict, NotGreen)
    assert verdict.contexts == (OffendingCheck(context="ci-green", state=expected),)


def test_an_unreadable_check_suites_read_refuses_with_a_named_reason():
    world = _green_world()
    del world[_SUITES]
    verdict, _ = _verdict(world=world)
    assert isinstance(verdict, NotGreen)
    assert "check results unreadable" in verdict.reason
