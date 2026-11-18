"""incident_merge_forge: the label and the effective required checks on the exact head.

Work-item livespec-dev-tooling-u3nbm3, slice B3 (contracts.md, the expedited
incident execution contract, the `Incident-merge principal.` paragraph). Every verdict
case builds the one world in which the head is green (`_world`), then breaks
exactly one fact and asserts the verdict is `NotGreen` naming the offending
context. The forge is a dict-backed fake keyed on the `gh` argument tail; an
argument tail the world does not hold answers as a failed read.
"""

from __future__ import annotations

import json

import pytest

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.incident_merge_forge import (
    CheckState,
    ForgeReader,
    Green,
    IncidentForgeReadError,
    NotGreen,
    OffendingCheck,
    has_incident_label,
    required_checks_verdict,
)

__all__: list[str] = []

_REPO = "o/r"
_HEAD = "h" * 40
_CLASSIC = f"repos/{_REPO}/branches/master/protection/required_status_checks"
_RULES = f"repos/{_REPO}/rules/branches/master?per_page=100"
_ACTIONS = f"repos/{_REPO}/actions/runs?head_sha={_HEAD}&per_page=100"
_CHECK_RUNS = f"repos/{_REPO}/commits/{_HEAD}/check-runs?per_page=100"
_STATUS = f"repos/{_REPO}/commits/{_HEAD}/status?per_page=100"
_PULL = f"repos/{_REPO}/pulls/7"
_STRAY_STATUS: list[dict[str, list[object]]] = [{"statuses": [3]}]
_NO_RULE_PAGES: list[list[object]] = [[]]
_EMPTY_PAGES: list[dict[str, object]] = [{}]


def _ok(*, body: object) -> GhRead:
    return GhRead(returncode=0, stdout=json.dumps(body), stderr="")


def _fail(*, stderr: str) -> GhRead:
    return GhRead(returncode=1, stdout="", stderr=stderr)


def _run(*, name: str, run_id: int, suite: int = 1, **over: object) -> dict[str, object]:
    run: dict[str, object] = {
        "id": run_id,
        "name": name,
        "head_sha": _HEAD,
        "status": "completed",
        "conclusion": "success",
        "check_suite": {"id": suite},
    }
    run.update(over)
    return run


def _world() -> dict[str, GhRead]:
    """The green world: classic requires `ci-green`, a ruleset requires `lint`."""
    rule = {
        "type": "required_status_checks",
        "ruleset_id": 9,
        "parameters": {"required_status_checks": [{"context": "lint"}]},
    }
    return {
        f"repos/{_REPO}": _ok(body={"default_branch": "master"}),
        _CLASSIC: _ok(body={"contexts": ["ci-green"], "strict": False}),
        _RULES: _ok(body=[[rule, {"type": "pull_request", "ruleset_id": 9}]]),
        _ACTIONS: _ok(
            body=[
                {
                    "workflow_runs": [
                        {"check_suite_id": 1, "event": "pull_request"},
                        {"check_suite_id": 2, "event": "merge_group"},
                    ]
                }
            ]
        ),
        _CHECK_RUNS: _ok(
            body=[{"check_runs": [_run(name="ci-green", run_id=10), _run(name="lint", run_id=11)]}]
        ),
        _STATUS: _ok(body=[{"statuses": [{"context": "lint", "state": "success"}]}]),
        _PULL: _ok(body={"labels": [{"name": "bug"}, {"name": "expedited-incident-response"}]}),
    }


def _forge(*, world: dict[str, GhRead]) -> ForgeReader:
    def read(*, args: list[str]) -> GhRead:
        return world.get(args[-1], _fail(stderr=f"HTTP 404: not in world {args[-1]}"))

    return read


def _verdict(*, world: dict[str, GhRead]) -> Green | NotGreen:
    return required_checks_verdict(forge=_forge(world=world), repo=_REPO, head_sha=_HEAD)


def _runs(*runs: dict[str, object]) -> GhRead:
    return _ok(body=[{"check_runs": list(runs)}])


def test_every_effective_context_success_on_the_head_is_green() -> None:
    assert _verdict(world=_world()) == Green(
        head_sha=_HEAD, contexts=frozenset({"ci-green", "lint"})
    )


@pytest.mark.parametrize(
    ("runs", "expected"),
    [
        ((_run(name="ci-green", run_id=10, conclusion="failure"),), "failing"),
        ((_run(name="ci-green", run_id=10, status="in_progress", conclusion=None),), "pending"),
        ((), "absent"),
        ((_run(name="ci-green", run_id=10, suite=2),), "merge-group-only"),
        ((_run(name="ci-green", run_id=10, suite=3),), "event-unknown"),
        ((_run(name="ci-green", run_id=10, head_sha="other"),), "absent"),
        (
            (
                _run(name="ci-green", run_id=10),
                _run(name="ci-green", run_id=12, conclusion="failure"),
            ),
            "failing",
        ),
    ],
)
def test_a_required_context_not_success_on_the_head_is_named(
    runs: tuple[dict[str, object], ...], expected: CheckState
) -> None:
    world = _world()
    world[_CHECK_RUNS] = _runs(*runs, _run(name="lint", run_id=11), {"name": 5})
    verdict = _verdict(world=world)
    assert isinstance(verdict, NotGreen)
    assert verdict.contexts == (OffendingCheck(context="ci-green", state=expected),)
    assert f"ci-green ({expected})" in verdict.reason


def test_the_latest_counted_run_decides_and_a_merge_group_run_does_not() -> None:
    world = _world()
    world[_CHECK_RUNS] = _runs(
        _run(name="ci-green", run_id=12),
        _run(name="ci-green", run_id=10, conclusion="failure"),
        _run(name="ci-green", run_id=13, suite=2, conclusion="failure"),
        _run(name="lint", run_id=11),
    )
    assert isinstance(_verdict(world=world), Green)


@pytest.mark.parametrize(("state", "expected"), [("failure", "failing"), ("pending", "pending")])
def test_a_commit_status_not_success_is_named(state: str, expected: CheckState) -> None:
    world = _world()
    world[_STATUS] = _ok(
        body=[{"statuses": [{"context": "lint", "state": state}, {"context": None}]}]
    )
    verdict = _verdict(world=world)
    assert isinstance(verdict, NotGreen)
    assert verdict.contexts == (OffendingCheck(context="lint", state=expected),)


def test_a_status_alone_satisfies_a_context_with_no_counted_run() -> None:
    world = _world()
    world[_CHECK_RUNS] = _runs(_run(name="ci-green", run_id=10))
    assert isinstance(_verdict(world=world), Green)


@pytest.mark.parametrize(
    ("path", "answer", "reason"),
    [
        (f"repos/{_REPO}", _fail(stderr="HTTP 500"), "default branch of o/r could not be read"),
        (f"repos/{_REPO}", GhRead(returncode=0, stdout="{", stderr=""), "default branch"),
        (f"repos/{_REPO}", _ok(body=[]), "default branch"),
        (_CLASSIC, _fail(stderr="HTTP 404: Branch not protected"), "has no branch protection"),
        (_CLASSIC, _fail(stderr="HTTP 403: Forbidden"), "classic required checks unreadable"),
        (_CLASSIC, _ok(body={"strict": False}), "carried no contexts list"),
        (_RULES, _fail(stderr="HTTP 502"), "ruleset rules unreadable"),
        (_RULES, _ok(body={"not": "pages"}), "not a list of rule pages"),
        (_ACTIONS, _fail(stderr="HTTP 500"), "check results unreadable"),
        (_CHECK_RUNS, GhRead(returncode=0, stdout="nope", stderr=""), "body was not strict JSON"),
        (_CHECK_RUNS, _ok(body={}), "not a list of pages"),
        (_CHECK_RUNS, _ok(body=_EMPTY_PAGES), "carried no check_runs list"),
        (_STATUS, _ok(body=_STRAY_STATUS), "statuses entry was not an object"),
        (_STATUS, _ok(body=[5]), "carried no statuses list"),
    ],
)
def test_an_unread_fact_is_not_green_and_says_why(path: str, answer: GhRead, reason: str) -> None:
    world = _world()
    world[path] = answer
    verdict = _verdict(world=world)
    assert isinstance(verdict, NotGreen)
    assert reason in verdict.reason
    assert verdict.contexts == ()


def test_status_checks_not_enabled_is_an_empty_classic_contribution() -> None:
    world = _world()
    world[_CLASSIC] = _fail(stderr="HTTP 404: Required status checks not enabled")
    verdict = _verdict(world=world)
    assert verdict == Green(head_sha=_HEAD, contexts=frozenset({"lint"}))


def test_an_empty_effective_set_is_not_vacuously_green() -> None:
    world = _world()
    world[_CLASSIC] = _ok(body={"contexts": [], "strict": False})
    world[_RULES] = _ok(body=_NO_RULE_PAGES)
    verdict = _verdict(world=world)
    assert isinstance(verdict, NotGreen)
    assert "is empty" in verdict.reason


def test_the_incident_label_is_read_from_the_pull_request() -> None:
    world = _world()
    labelled = has_incident_label(forge=_forge(world=world), repo=_REPO, pr_number=7)
    world[_PULL] = _ok(body={"labels": [{"name": "bug"}, "stray"]})
    unlabelled = has_incident_label(forge=_forge(world=world), repo=_REPO, pr_number=7)
    assert (labelled, unlabelled) == (True, False)


@pytest.mark.parametrize(
    "answer",
    [
        _fail(stderr="HTTP 404"),
        GhRead(returncode=0, stdout="<html>", stderr=""),
        _ok(body={"title": "no labels"}),
    ],
)
def test_an_unread_pull_request_is_never_reported_unlabelled(answer: GhRead) -> None:
    world = _world()
    world[_PULL] = answer
    with pytest.raises(IncidentForgeReadError):
        _ = has_incident_label(forge=_forge(world=world), repo=_REPO, pr_number=7)
