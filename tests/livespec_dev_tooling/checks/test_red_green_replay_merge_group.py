"""The replay gate admits a rebased expedited commit in a merge group by queue attribution.

Scenarios "the replay gate admits a rebased expedited commit in a merge group by its
verbatim patch-id", "the replay gate convicts a merge-group commit whose patch-id
matches nothing recorded" and "the replay gate attributes each commit of a batched
merge group to its own pull request" (livespec-dev-tooling-txon2s).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_ci_authority
from livespec_dev_tooling.checks import _red_green_replay_incident as incident
from livespec_dev_tooling.checks import _red_green_replay_merge_group as merge_group
from livespec_dev_tooling.incident_git import IncidentGitError

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-txon2s
_ITEM = "livespec-dev-tooling-item"
_BASE = "a" * 40
_HEAD = "b" * 40
_SHA = "c" * 40
_RECORDED = "4" * 40
_SECOND = "5" * 40
_TRAILER = "Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: " + _ITEM
_MESSAGE = "fix: repair\n\n" + _TRAILER + "\n"
_REFUSED = "incident-provenance-refused: " + _SHA + ": "


def _body(*, number: int = 7) -> str:
    arm = {
        "repository": "owner/repo",
        "incident_item_id": _ITEM,
        "attempt_id": "attempt-1",
        "operation_id": "operation-2",
        "generation": 2,
        "owner": "operator",
        "phase": "repair",
        "pr_number": number,
        "base_sha": _BASE,
        "head_sha": _HEAD,
        "required_jobs": ["ci-green"],
        "controller_release": "v1.0.0",
        "controller_revision": "d" * 40,
        "authority_receipt": b"{}".hex(),
    }
    arm_id = hashlib.sha256(json.dumps(arm, sort_keys=True).encode()).hexdigest()
    payload = json.dumps({"schema": 1, "arm": arm, "observer_arm_id": arm_id})
    return "repair\n\n<!-- livespec-incident-ci\n" + payload + "\n-->\n"


def _entry(*, number: int, base: str, head: str) -> dict[str, Any]:
    return {
        "position": number,
        "pullRequest": {"number": number},
        "baseCommit": {"oid": base},
        "headCommit": {"oid": head},
    }


def _world() -> dict[str, Any]:
    """One queued pull request whose single rebased commit copies its single recorded one."""
    return {
        "entries": [_entry(number=7, base="1" * 40, head="2" * 40)],
        "ranges": {f"{'1' * 40}..{'2' * 40}": [_SHA], f"{_BASE}..{_HEAD}": [_RECORDED]},
        "pids": {_SHA: "pid-1", _RECORDED: "pid-1"},
        "pulls": {
            7: {"number": 7, "body": _body(), "base": {"sha": _BASE}, "head": {"sha": _HEAD}}
        },
        "graphql_rc": 0,
        "graphql_text": None,
        "pull_rc": 0,
        "fetch_rc": 0,
        "raising": set(),
    }


def _forge_double(*, world: dict[str, Any]) -> Mock:
    def gh(*, args: list[str]) -> SimpleNamespace:
        if args[1] == "graphql":
            nodes = world["entries"]
            text = world["graphql_text"] or json.dumps(
                {"data": {"repository": {"mergeQueue": {"entries": {"nodes": nodes}}}}}
            )
            return SimpleNamespace(returncode=world["graphql_rc"], stdout=text, stderr="")
        number = int(args[1].rsplit("/", 1)[1])
        return SimpleNamespace(
            returncode=world["pull_rc"], stdout=json.dumps(world["pulls"][number]), stderr=""
        )

    return Mock(side_effect=gh)


def _git_answer(*, world: dict[str, Any], args: list[str], data: bytes | None) -> tuple[int, str]:
    """The (exit code, stdout) the double git gives one call."""
    name = args[0]
    if name == "rev-list":
        lines = world["ranges"].get(args[1])
        return (1, "") if lines is None else (0, "\n".join(lines))
    if name == "show":
        return 0, "diff-" + args[2]
    if name == "patch-id":
        sha = (data or b"").decode().removeprefix("diff-")
        pid = world["pids"].get(sha)
        return 0, "" if pid is None else f"{pid} {sha}\n"
    return (world["fetch_rc"], "") if name == "fetch" else (0, "")


def _git_double(*, world: dict[str, Any]) -> Mock:
    def git(
        *, repo: Path, args: list[str], data: bytes | None = None, check: bool = True
    ) -> SimpleNamespace:
        _ = (repo, check)
        if args[0] in world["raising"]:
            raise IncidentGitError(reason="boom", cmd=tuple(args), returncode=None, stderr=b"")
        code, text = _git_answer(world=world, args=args, data=data)
        return SimpleNamespace(returncode=code, stdout=text.encode(), stderr=b"")

    return Mock(side_effect=git)


def _install(*, world: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> tuple[Mock, Mock]:
    forge, runner = _forge_double(world=world), _git_double(world=world)
    monkeypatch.setattr(merge_group, "gh_read", forge)
    monkeypatch.setattr(merge_group, "run_git", runner)

    def tree(**_kwargs: object) -> str:
        return "e" * 40

    monkeypatch.setattr(incident, "git_text", tree)
    return forge, runner


@pytest.fixture
def observer(monkeypatch: pytest.MonkeyPatch) -> Mock:
    answer = Mock(return_value=True)

    def provenance(_self: object, *, query: object) -> object:
        return answer(query=query)

    monkeypatch.setattr(
        incident_ci_authority.CiAuthorityBoundary, "provenance", provenance, raising=False
    )
    return answer


def _environ(*, tmp_path: Path, configured: bool = True) -> dict[str, str]:
    event = tmp_path / "event.json"
    _ = event.write_text(json.dumps({"merge_group": {"base_ref": "refs/heads/master"}}))
    environ = {
        "GITHUB_EVENT_NAME": "merge_group",
        "GITHUB_EVENT_PATH": str(event),
        "GITHUB_REPOSITORY": "owner/repo",
    }
    if configured:
        environ["LIVESPEC_INCIDENT_OBSERVER_URL"] = "https://controller.example"
        environ["LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"] = "query-token"
    return environ


def test_a_rebased_copy_with_one_recorded_counterpart_is_admitted(
    tmp_path: Path, observer: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    forge, runner = _install(world=_world(), monkeypatch=monkeypatch)
    admitted = incident.admitted_by_recorded_incident(
        sha=_SHA, message=_MESSAGE, environ=_environ(tmp_path=tmp_path)
    )
    fetched = [
        call.kwargs["args"] for call in runner.call_args_list if call.kwargs["args"][0] == "fetch"
    ]
    verbatim = [
        call.kwargs["args"]
        for call in runner.call_args_list
        if call.kwargs["args"][0] == "patch-id"
    ]
    queue_read = forge.call_args_list[0].kwargs["args"]
    facts = [
        admitted is True,
        observer.call_args.kwargs["query"]["pr_number"] == 7,
        observer.call_args.kwargs["query"]["head"] == _HEAD,
        fetched == [["fetch", "--no-tags", "origin", "refs/pull/7/head"]],
        all(args == ["patch-id", "--verbatim"] for args in verbatim),
        "branch=master" in queue_read,
        "owner=owner" in queue_read and "name=repo" in queue_read,
    ]
    assert all(facts)


def test_each_commit_of_a_batched_group_is_judged_against_its_own_pull_request(
    tmp_path: Path, observer: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = _world()
    world["entries"] = [
        _entry(number=7, base="1" * 40, head="2" * 40),
        _entry(number=9, base="2" * 40, head="3" * 40),
    ]
    world["ranges"][f"{'2' * 40}..{'3' * 40}"] = [_SECOND]
    world["ranges"][f"{_BASE}..{_HEAD}"] = [_RECORDED]
    world["ranges"][f"{'1' * 40}..{'2' * 40}"] = ["6" * 40]
    world["pids"] |= {"6" * 40: "pid-other", _SECOND: "pid-1"}
    world["pulls"][9] = {
        "number": 9,
        "body": _body(number=9),
        "base": {"sha": _BASE},
        "head": {"sha": _HEAD},
    }
    forge, _runner = _install(world=world, monkeypatch=monkeypatch)
    admitted = incident.admitted_by_recorded_incident(
        sha=_SECOND,
        message=_MESSAGE,
        environ=_environ(tmp_path=tmp_path),
    )
    read = [call.kwargs["args"][1] for call in forge.call_args_list]
    facts = [
        admitted is True,
        observer.call_args.kwargs["query"]["pr_number"] == 9,
        "repos/owner/repo/pulls/9" in read,
        "repos/owner/repo/pulls/7" not in read,
    ]
    assert all(facts), read


def _no_range(world: dict[str, Any]) -> None:
    world["ranges"][f"{'1' * 40}..{'2' * 40}"] = ["9" * 40]


def _two_ranges(world: dict[str, Any]) -> None:
    world["entries"].append(_entry(number=9, base="7" * 40, head="8" * 40))
    world["ranges"][f"{'7' * 40}..{'8' * 40}"] = [_SHA]


def _entries_unreadable(world: dict[str, Any]) -> None:
    world["graphql_rc"] = 1


def _entries_malformed(world: dict[str, Any]) -> None:
    world["graphql_text"] = "not json"


def _entries_missing(world: dict[str, Any]) -> None:
    world["graphql_text"] = "{}"


def _range_listing_raises(world: dict[str, Any]) -> None:
    world["raising"].add("rev-list")


def _pull_unreadable(world: dict[str, Any]) -> None:
    world["pull_rc"] = 1


def _no_block(world: dict[str, Any]) -> None:
    world["pulls"][7]["body"] = "no block here"


def _undecodable(world: dict[str, Any]) -> None:
    world["pulls"][7]["body"] = "x\n<!-- livespec-incident-ci\n{}\n-->\n"


def _identity_differs(world: dict[str, Any]) -> None:
    world["pulls"][7]["head"] = {"sha": "f" * 40}


def _fetch_fails(world: dict[str, Any]) -> None:
    world["fetch_rc"] = 128


def _no_patch_id(world: dict[str, Any]) -> None:
    del world["pids"][_SHA]


def _patch_id_unreadable(world: dict[str, Any]) -> None:
    world["raising"].add("show")


def _recorded_unlistable(world: dict[str, Any]) -> None:
    del world["ranges"][f"{_BASE}..{_HEAD}"]


def _patch_id_mismatch(world: dict[str, Any]) -> None:
    world["pids"][_RECORDED] = "pid-other"


def _two_recorded(world: dict[str, Any]) -> None:
    world["ranges"][f"{_BASE}..{_HEAD}"] = [_RECORDED, _SECOND]
    world["pids"][_SECOND] = "pid-1"


def _two_queued_copies(world: dict[str, Any]) -> None:
    world["ranges"][f"{'1' * 40}..{'2' * 40}"] = [_SHA, _SECOND]
    world["pids"][_SECOND] = "pid-1"


CONVICTIONS = {
    "no queue range contains it": (_no_range, "no merge queue entry range contains it"),
    "two queue ranges contain it": (_two_ranges, "more than one merge queue entry range"),
    "queue read fails": (_entries_unreadable, "merge queue entries could not be read"),
    "queue answer malformed": (_entries_malformed, "merge queue entries could not be read"),
    "queue answer has no entries": (_entries_missing, "merge queue entries could not be read"),
    "range listing raises": (_range_listing_raises, "no merge queue entry range contains it"),
    "pull request unreadable": (_pull_unreadable, "pull request 7 could not be read"),
    "no block": (_no_block, "no livespec-incident-ci block was read"),
    "block does not decode": (_undecodable, "the livespec-incident-ci block does not decode"),
    "identity differs from the forge": (_identity_differs, "different pull request, base or head"),
    "fetch fails": (_fetch_fails, "the fetch of refs/pull/7/head failed"),
    "no patch-id": (_no_patch_id, "no patch-id"),
    "patch-id unreadable": (_patch_id_unreadable, "no patch-id"),
    "recorded range unlistable": (_recorded_unlistable, "could not be listed"),
    "patch-id mismatch": (_patch_id_mismatch, "patch-id mismatch"),
    "two recorded counterparts": (_two_recorded, "patch-id mismatch"),
    "two queued copies": (_two_queued_copies, "patch-id mismatch"),
}


@pytest.mark.parametrize("label", sorted(CONVICTIONS))
def test_every_other_outcome_stays_convicted_naming_the_first_failed_condition(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    label: str,
) -> None:
    mutate, wanted = CONVICTIONS[label]
    world = _world()
    mutate(world)
    _ = _install(world=world, monkeypatch=monkeypatch)
    admitted = incident.admitted_by_recorded_incident(
        sha=_SHA, message=_MESSAGE, environ=_environ(tmp_path=tmp_path)
    )
    err = capsys.readouterr().err
    facts = [admitted is False, err.startswith(_REFUSED), wanted in err, observer.call_count == 0]
    assert all(facts), (label, err)


def test_an_unreadable_event_convicts_by_the_unreadable_queue(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _install(world=_world(), monkeypatch=monkeypatch)
    environ = _environ(tmp_path=tmp_path) | {"GITHUB_EVENT_PATH": str(tmp_path / "absent.json")}
    admitted = incident.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    err = capsys.readouterr().err
    assert (admitted, "merge queue entries could not be read" in err, observer.call_count) == (
        False,
        True,
        0,
    )


def test_a_commit_without_the_audited_trailer_stays_convicted(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _install(world=_world(), monkeypatch=monkeypatch)
    admitted = incident.admitted_by_recorded_incident(
        sha=_SHA, message="fix: repair\n", environ=_environ(tmp_path=tmp_path)
    )
    err = capsys.readouterr().err
    assert (admitted, "no audited trailer naming the incident" in err, observer.call_count) == (
        False,
        True,
        0,
    )


def test_an_unconfigured_observer_fails_closed_in_a_merge_group(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _ = _install(world=_world(), monkeypatch=monkeypatch)
    admitted = incident.admitted_by_recorded_incident(
        sha=_SHA, message=_MESSAGE, environ=_environ(tmp_path=tmp_path, configured=False)
    )
    err = capsys.readouterr().err
    assert (admitted, "not configured" in err, observer.call_count) == (False, True, 0)


def test_a_head_the_observer_does_not_record_stays_convicted(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    observer.return_value = False
    _ = _install(world=_world(), monkeypatch=monkeypatch)
    admitted = incident.admitted_by_recorded_incident(
        sha=_SHA, message=_MESSAGE, environ=_environ(tmp_path=tmp_path)
    )
    err = capsys.readouterr().err
    assert (admitted, "the observer does not record this head" in err) == (False, True)
