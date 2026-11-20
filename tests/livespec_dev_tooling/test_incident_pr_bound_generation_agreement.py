"""The hook, the CI entrance and the replay gate admit one pr-bound generation for one PR."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from livespec_dev_tooling import incident_hook_scope as hook_module
from livespec_dev_tooling.checks import _red_green_replay_incident as replay_module
from livespec_dev_tooling.incident_ci_payload import query_for
from livespec_dev_tooling.incident_ci_policy import (
    CiAuthority,
    CiEvent,
    CiPlan,
    CiTarget,
    CiTrust,
    select_ci_plan,
)
from tests.livespec_dev_tooling import test_incident_hook_scope_base as hook_test

_LABEL = "expedited-incident-response"
_TRAILER = "Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: incident"
_ENVIRON = {
    "GITHUB_EVENT_NAME": "pull_request",
    "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example",
    "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "token",
}


def authority() -> CiAuthority:
    """The arm for the moved-master attempt: keyed on the attempt's PR base and head."""
    attempt = hook_test.moved_master_attempt()
    context = hook_test.context()
    identity = context.identity
    assert identity is not None
    assert (identity.base_sha, identity.head_sha) == (attempt["base"], attempt["head"])
    return CiAuthority(
        context=context,
        generation=3,
        owner="owner",
        pr_number=attempt["pr_number"],
        receipt_digest="e" * 64,
        observer_arm_id="f" * 64,
    )


def event(*, base: str) -> CiEvent:
    attempt = hook_test.moved_master_attempt()
    return CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha=base,
        head_sha=attempt["head"],
        pr_number=attempt["pr_number"],
        labels=(_LABEL,),
    )


def ci_entrance(*, base: str) -> tuple[CiPlan | object, list[dict[str, Any]]]:
    """Drive the real CI entrance, recording the query both authority readers receive."""
    queries: list[dict[str, Any]] = []
    auth = authority()
    query = query_for(authority=auth)

    def current(_authority: CiAuthority) -> bool:
        queries.append(query)
        return True

    def observer(_authority: CiAuthority, _event: CiEvent) -> bool:
        queries.append(query)
        return True

    result = select_ci_plan(
        event=event(base=base),
        targets=(CiTarget(name="check-fast", classification="fast"),),
        authority=auth,
        trust=CiTrust(current=current, observer=observer),
        environ={},
    )
    return result, queries


def install_replay(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, *, base: str
) -> list[dict[str, Any]]:
    """Fake the replay gate's event file, git reads and observer; return the asked queries."""
    attempt = hook_test.moved_master_attempt()
    path = tmp_path / "event.json"
    pull = dict(
        number=attempt["pr_number"],
        body="body",
        base=dict(sha=base),
        head=dict(sha=attempt["head"]),
    )
    path.write_text(json.dumps(dict(pull_request=pull)), encoding="utf-8")
    asked: list[dict[str, Any]] = []

    class Boundary:
        def __init__(self, **_kwargs: Any) -> None:
            return

        def provenance(self, *, query: dict[str, Any]) -> bool:
            asked.append(query)
            return True

    _EVENT_PATH.append(str(path))
    monkeypatch.setattr(replay_module, "incident_block", lambda **_kwargs: "payload")
    monkeypatch.setattr(replay_module, "decode_authority", lambda **_kwargs: authority())
    monkeypatch.setattr(replay_module, "run_git", lambda **_kwargs: SimpleNamespace(returncode=0))
    monkeypatch.setattr(replay_module, "git_text", lambda **_kwargs: "d" * 40)
    monkeypatch.setattr(replay_module, "CiAuthorityBoundary", Boundary)
    return asked


_EVENT_PATH: list[str] = []


def replay(*, sha: str) -> bool:
    environ = {**_ENVIRON, "GITHUB_EVENT_PATH": _EVENT_PATH[-1]}
    return replay_module.admitted_by_recorded_incident(
        sha=sha, message="subject\n\n" + _TRAILER + "\n", environ=environ
    )


def test_hook_ci_entrance_and_replay_gate_admit_the_same_pr_bound_generation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    attempt = hook_test.moved_master_attempt()
    hook_test.install(monkeypatch, branch_point_diff="app.py")
    hooked = hook_test.run(hook_module.HookCall(hook="pre-commit", extra=(), stdin=""), tmp_path)
    assert hooked["original_paths"] == ["app.py"]

    plan, queries = ci_entrance(base=attempt["base"])
    assert isinstance(plan, CiPlan)
    assert len(queries) == 2

    asked = install_replay(monkeypatch, tmp_path, base=attempt["base"])
    assert replay(sha="c" * 40) is True

    wanted = (attempt["pr_number"], attempt["base"], attempt["head"])
    for query in queries:
        assert (query["pr_number"], query["base_sha"], query["head_sha"]) == wanted
    for query in asked:
        assert (query["pr_number"], query["base"], query["head"]) == wanted
    assert asked[0]["generation"] == authority().generation


def test_ci_entrance_and_replay_gate_refuse_the_branch_point_as_the_pr_base(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # The entrance no longer compares the event base itself: the independent observer
    # judges a moved base against the controller's freshness bound.
    plan = select_ci_plan(
        event=event(base=hook_test.BRANCH_POINT),
        targets=(CiTarget(name="check-fast", classification="fast"),),
        authority=authority(),
        trust=CiTrust(
            current=lambda _authority: True,
            observer=lambda _authority, seen: seen.base_sha != hook_test.BRANCH_POINT,
        ),
        environ={},
    )
    assert not isinstance(plan, CiPlan)

    asked = install_replay(monkeypatch, tmp_path, base=hook_test.BRANCH_POINT)
    assert replay(sha="c" * 40) is False
    assert asked == []
