"""The incident-merge principal composes its three halves and records every outcome.

Work-item livespec-dev-tooling-u3nbm3, slice B4 (contracts.md, the expedited incident
execution contract, the `Incident-merge principal.` paragraph). Each case builds the
one world in which the merge happens (`_World`), then breaks exactly one fact and
asserts the named refusal, that nothing was merged, and that the refusal was
recorded on the incident work item.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pytest
from returns.result import Failure, Result, Success

import livespec_dev_tooling.incident_merge_principal as principal_module
from livespec_dev_tooling.incident_authority_client import AuthorityRefusal
from livespec_dev_tooling.incident_merge_forge import (
    Green,
    IncidentForgeReadError,
    NotGreen,
    OffendingCheck,
)
from livespec_dev_tooling.incident_merge_principal import (
    Merged,
    QueueUnreadableError,
    Refused,
    merge_incident_repair,
    queue_entries_ahead,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-u3nbm3

_REPO = "o/r"
_BASE = "b" * 40
_HEAD = "c" * 40
_MASTER = "d" * 40
_NOW = datetime(2026, 11, 18, 9, 30, 15, tzinfo=timezone.utc)
_Answer = tuple[int, object]
_Chain = Callable[..., Result[dict[str, Any], AuthorityRefusal]]


def _attempt() -> dict[str, object]:
    return {
        "item_id": "inc-1",
        "phase": "repair",
        "base": _BASE,
        "head": _HEAD,
        "pr_number": 7,
        "carrier": {"state": "pr-bound"},
    }


def _chain(*, incident_id: str) -> Result[dict[str, Any], AuthorityRefusal]:
    assert incident_id == "inc-1"
    return Success({"genesis_writer": "file-incident", "attempt": _attempt(), "is_current": True})


def _pull(**over: object) -> dict[str, object]:
    pull: dict[str, object] = {
        "state": "open",
        "merged": False,
        "base": {"sha": _BASE, "ref": "master", "repo": {"default_branch": "master"}},
        "head": {"sha": _HEAD},
        "merge_commit_sha": _MASTER,
    }
    pull.update(over)
    return pull


@dataclass
class _World:
    """One forge: scripted answers per (method, path), a call log and the recorded text."""

    answers: dict[tuple[str, str], list[_Answer]] = field(default_factory=dict)
    calls: list[tuple[str, str, object]] = field(default_factory=list)
    records: list[str] = field(default_factory=list)
    sleeps: list[float] = field(default_factory=list)

    def request(self, *, method: str, path: str, value: object | None = None) -> _Answer:
        self.calls.append((method, path, value))
        scripted = self.answers[(method, path)]
        return scripted.pop(0) if len(scripted) > 1 else scripted[0]

    def record(self, *, incident_id: str, text: str) -> None:
        assert incident_id == "inc-1"
        self.records.append(text)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)

    def merge_calls(self) -> list[tuple[str, str, object]]:
        return [call for call in self.calls if call[0] == "PUT"]


def _world(*, merge_path: str = "pulls/7/merge-async", merge_answer: _Answer = (202, {})) -> _World:
    return _World(
        answers={
            ("GET", "pulls/7"): [(200, _pull()), (200, _pull(merged=True))],
            ("PUT", merge_path): [merge_answer],
        }
    )


@pytest.fixture(autouse=True)
def _green_forge_halves(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(principal_module, "has_incident_label", lambda **_: True)
    monkeypatch.setattr(
        principal_module,
        "required_checks_verdict",
        lambda **_: Green(head_sha=_HEAD, contexts=frozenset({"ci-green"})),
    )


def _three(**_: object) -> tuple[int, ...]:
    return (3,)


def _merge(
    *,
    world: _World,
    endpoint: str | None = None,
    queue: Callable[..., tuple[int, ...]] = _three,
    chain: _Chain = _chain,
) -> Merged | Refused:
    extra: dict[str, object] = {} if endpoint is None else {"endpoint": endpoint}
    return merge_incident_repair(
        repo=_REPO,
        incident_id="inc-1",
        pr_number=7,
        principal="incident-merge App 5812830",
        forge=world,
        check_reader=lambda **_: None,
        chain=chain,
        queue=queue,
        record=world.record,
        clock=lambda: _NOW,
        sleep=world.sleep,
        **extra,
    )


def test_a_verified_repair_is_rebase_merged_with_its_expected_head_and_recorded() -> None:
    world = _world()
    outcome = _merge(world=world)
    assert outcome == Merged(
        incident_id="inc-1",
        pr_number=7,
        principal="incident-merge App 5812830",
        head_sha=_HEAD,
        master_sha=_MASTER,
        merged_at="2026-11-18T09:30:15Z",
        queue_ahead=(3,),
        endpoint="merge-async",
    )
    assert world.merge_calls() == [
        (
            "PUT",
            "pulls/7/merge-async",
            {"merge_method": "rebase", "sha": _HEAD, "bypass_rules": True},
        )
    ]
    assert world.records == [
        "incident-merge: merged\n"
        "principal: incident-merge App 5812830\n"
        "pull-request: 7\n"
        f"head-sha: {_HEAD}\n"
        f"master-sha: {_MASTER}\n"
        "merged-at: 2026-11-18T09:30:15Z\n"
        "queue-ahead: 3\n"
        "endpoint: merge-async"
    ]


def test_the_synchronous_endpoint_is_one_flag_away() -> None:
    world = _world(merge_path="pulls/7/merge", merge_answer=(200, {"merged": True}))
    outcome = _merge(world=world, endpoint="merge")
    assert isinstance(outcome, Merged)
    assert outcome.endpoint == "merge"
    assert world.merge_calls() == [
        ("PUT", "pulls/7/merge", {"merge_method": "rebase", "sha": _HEAD})
    ]


def _unreadable_queue(**_: object) -> tuple[int, ...]:
    raise QueueUnreadableError(detail="graphql 502")


def _empty_queue(**_: object) -> tuple[int, ...]:
    return ()


def test_an_empty_or_unreadable_queue_is_recorded_and_never_blocks_the_merge() -> None:
    empty = _world()
    assert isinstance(_merge(world=empty, queue=_empty_queue), Merged)
    assert "queue-ahead: none" in empty.records[0]

    blind = _world()
    outcome = _merge(world=blind, queue=_unreadable_queue)
    assert isinstance(outcome, Merged)
    assert outcome.queue_ahead is None
    assert "queue-ahead: unreadable: graphql 502" in blind.records[0]


def _refusal(
    *, world: _World, reason: str, chain: _Chain = _chain, merge_attempts: int = 0
) -> Refused:
    outcome = _merge(world=world, chain=chain)
    assert isinstance(outcome, Refused)
    assert outcome.reason == reason
    assert len(world.merge_calls()) == merge_attempts
    assert world.records == [
        f"incident-merge: refused\nreason: {reason}\ndetail: {outcome.detail}\npull-request: 7"
    ]
    return outcome


def _missing(*, incident_id: str) -> Result[dict[str, Any], AuthorityRefusal]:
    return Failure(AuthorityRefusal(code="no-genesis", detail=incident_id))


def test_a_chain_that_cannot_establish_a_genesis_refuses_without_merging() -> None:
    outcome = _refusal(world=_world(), reason="no-genesis-record", chain=_missing)
    assert "no-genesis: inc-1" in outcome.detail


def test_a_pull_request_the_chain_binds_elsewhere_refuses_with_the_chains_reason() -> None:
    world = _world()
    world.answers[("GET", "pulls/7")] = [(200, _pull(head={"sha": "e" * 40}))]
    _refusal(world=world, reason="base-head-mismatch")


def test_a_pull_request_without_the_incident_label_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(principal_module, "has_incident_label", lambda **_: False)
    _refusal(world=_world(), reason="label-absent")


def test_an_unreadable_label_read_refuses_rather_than_reading_as_unlabelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreadable(**_: object) -> bool:
        raise IncidentForgeReadError(path="pulls/7", detail="HTTP 502")

    monkeypatch.setattr(principal_module, "has_incident_label", unreadable)
    outcome = _refusal(world=_world(), reason="forge-unreadable")
    assert "HTTP 502" in outcome.detail


def test_a_required_check_not_green_refuses_naming_the_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    red = NotGreen(
        head_sha=_HEAD,
        reason="required checks not green: check-lint (failing)",
        contexts=(OffendingCheck(context="check-lint", state="failing"),),
    )
    monkeypatch.setattr(principal_module, "required_checks_verdict", lambda **_: red)
    outcome = _refusal(world=_world(), reason="checks-not-green")
    assert outcome.detail == "required checks not green: check-lint (failing)"


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ((404, {}), "forge-unreadable"),
        ((200, ["not", "an", "object"]), "forge-unreadable"),
        ((200, _pull(state="closed")), "pull-request-not-open"),
        ((200, _pull(merged=True)), "pull-request-not-open"),
        ((200, _pull(head={})), "forge-unreadable"),
        (
            (200, _pull(base={"sha": _BASE, "ref": "dev", "repo": {"default_branch": "master"}})),
            "default-branch-mismatch",
        ),
    ],
)
def test_a_pull_request_that_cannot_be_merged_as_read_is_refused(
    answer: _Answer, reason: str
) -> None:
    world = _world()
    world.answers[("GET", "pulls/7")] = [answer]
    _refusal(world=world, reason=reason)


@pytest.mark.parametrize(
    ("answer", "reason"),
    [
        ((409, {"message": "Head branch was modified"}), "head-moved"),
        ((405, {"message": "Repository rule violations found"}), "merge-rejected"),
        ((0, None), "merge-rejected"),
    ],
)
def test_a_forge_that_will_not_merge_is_a_named_refusal(answer: _Answer, reason: str) -> None:
    outcome = _refusal(world=_world(merge_answer=answer), reason=reason, merge_attempts=1)
    assert f"HTTP {answer[0]}" in outcome.detail


def test_a_merge_the_forge_never_confirms_is_recorded_as_unconfirmed() -> None:
    world = _world()
    world.answers[("GET", "pulls/7")] = [(200, _pull())]
    outcome = _refusal(world=world, reason="merge-unconfirmed", merge_attempts=1)
    assert "not merged after 5 reads" in outcome.detail
    assert world.sleeps == [2.0, 2.0, 2.0, 2.0]


_NODES = [
    {"position": 1, "pullRequest": {"number": 4}},
    {"position": 2, "pullRequest": {"number": 7}},
    {"position": 3, "pullRequest": {"number": 9}},
]


def _graphql(*nodes: object) -> object:
    return {"data": {"repository": {"mergeQueue": {"entries": {"nodes": list(nodes)}}}}}


def test_queue_entries_ahead_are_those_before_the_pull_request_or_all_when_not_queued() -> None:
    assert queue_entries_ahead(payload=_graphql(*_NODES), pr_number=7) == (4,)
    assert queue_entries_ahead(payload=_graphql(*_NODES), pr_number=99) == (4, 7, 9)
    assert queue_entries_ahead(payload=_graphql(), pr_number=7) == ()
    no_queue = {"data": {"repository": {"mergeQueue": None}}}
    assert queue_entries_ahead(payload=no_queue, pr_number=7) == ()


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {"errors": [{"message": "boom"}]},
        {"data": {"repository": {"mergeQueue": {"entries": {"nodes": "x"}}}}},
        _graphql({"position": "1", "pullRequest": {"number": 4}}),
        _graphql({"position": 1, "pullRequest": {}}),
        _graphql(5),
    ],
)
def test_a_queue_answer_that_does_not_parse_is_unreadable(payload: object) -> None:
    with pytest.raises(QueueUnreadableError):
        queue_entries_ahead(payload=payload, pr_number=7)
