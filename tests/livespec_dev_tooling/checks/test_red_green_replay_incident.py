"""The range gate admits an expedited commit only on recorded incident provenance."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from returns.io import IOSuccess

from livespec_dev_tooling import incident_ci_authority
from livespec_dev_tooling.checks import _red_green_replay_incident as module
from livespec_dev_tooling.checks import red_green_replay

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
_ITEM = "livespec-dev-tooling-item"
_BASE = "a" * 40
_HEAD = "b" * 40
_SHA = "c" * 40
_TRAILER = "Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: " + _ITEM
_MESSAGE = "fix: repair\n\n" + _TRAILER + "\n"


def _body() -> str:
    arm = {
        "repository": "owner/repo",
        "incident_item_id": _ITEM,
        "attempt_id": "attempt-1",
        "operation_id": "operation-2",
        "generation": 2,
        "owner": "operator",
        "phase": "repair",
        "pr_number": 7,
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


def _environ(*, tmp_path: Path, **pull_request: object) -> dict[str, str]:
    """A pull_request event with no label and no incident flag anywhere in it."""
    event = tmp_path / "event.json"
    fields = {
        "number": 7,
        "body": _body(),
        "base": {"sha": _BASE},
        "head": {"sha": _HEAD},
        "labels": [],
    }
    event.write_text(json.dumps({"pull_request": fields | pull_request}), encoding="utf-8")
    return {
        "GITHUB_EVENT_NAME": "pull_request",
        "GITHUB_EVENT_PATH": str(event),
        "LIVESPEC_INCIDENT_OBSERVER_URL": "https://controller.example",
        "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "query-token",
    }


@pytest.fixture
def observer(monkeypatch: pytest.MonkeyPatch) -> Mock:
    answer = Mock(return_value=True)
    monkeypatch.setattr(
        incident_ci_authority.CiAuthorityBoundary,
        "provenance",
        lambda _self, *, query: answer(query=query),
        raising=False,
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=SimpleNamespace(returncode=0, stdout=b"e" * 40 + b"\n", stderr=b"")),
    )
    return answer


def test_a_commit_the_chain_records_is_admitted_with_no_label_or_flag(
    tmp_path: Path, observer: Mock
) -> None:
    environ = _environ(tmp_path=tmp_path)
    admitted = module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert admitted is True
    assert observer.call_args.kwargs["query"] == {
        "repository": "owner/repo",
        "item_id": _ITEM,
        "attempt_id": "attempt-1",
        "phase": "repair",
        "operation_id": "operation-2",
        "generation": 2,
        "owner": "operator",
        "base": _BASE,
        "head": _HEAD,
        "pr_number": 7,
        "commit_sha": _HEAD,
        "tree_sha": "e" * 40,
    }


def test_the_trailer_alone_is_not_provenance_when_the_observer_does_not_record_it(
    tmp_path: Path, observer: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    observer.return_value = False
    environ = _environ(tmp_path=tmp_path)
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert "does not record this head" in capsys.readouterr().err
    assert observer.call_count == 1


@pytest.mark.parametrize(
    ("pull_request", "message", "named"),
    [
        ({"body": "<!-- livespec-incident-ci\n{}\n-->"}, _MESSAGE, "does not decode"),
        ({"number": 8}, _MESSAGE, "different pull request"),
        ({"base": {"sha": "f" * 40}}, _MESSAGE, "different pull request"),
        ({"head": {"sha": "f" * 40}}, _MESSAGE, "different pull request"),
        ({}, "fix: repair\n\nFactory-Override: anything\n", "no audited trailer"),
    ],
)
def test_a_mismatch_is_refused_by_name_before_asking_the_observer(
    tmp_path: Path,
    observer: Mock,
    capsys: pytest.CaptureFixture[str],
    pull_request: dict[str, object],
    message: str,
    named: str,
) -> None:
    environ = _environ(tmp_path=tmp_path, **pull_request)
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=message, environ=environ)
    assert named in capsys.readouterr().err
    assert observer.call_count == 0


def test_a_commit_outside_the_recorded_head_is_refused(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        subprocess,
        "run",
        Mock(return_value=SimpleNamespace(returncode=1, stdout=b"", stderr=b"")),
    )
    environ = _environ(tmp_path=tmp_path)
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert "not in the recorded head's history" in capsys.readouterr().err
    assert observer.call_count == 0


@pytest.mark.parametrize(
    "failure", [OSError("no git"), subprocess.TimeoutExpired(["git", "merge-base"], 1)]
)
def test_a_git_call_that_cannot_run_is_refused_by_name_not_raised(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
) -> None:
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=failure))
    environ = _environ(tmp_path=tmp_path)
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert "incident git merge-base " in capsys.readouterr().err
    assert observer.call_count == 0


def test_a_tree_that_cannot_be_read_is_refused_by_name_not_raised(
    tmp_path: Path,
    observer: Mock,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    answers = iter(
        [
            SimpleNamespace(returncode=0, stdout=b"", stderr=b""),
            SimpleNamespace(returncode=128, stdout=b"", stderr=b"bad object"),
        ]
    )
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: next(answers))
    environ = _environ(tmp_path=tmp_path)
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert "incident git rev-parse exited 128: bad object" in capsys.readouterr().err
    assert observer.call_count == 0


@pytest.mark.parametrize(
    "missing", ["LIVESPEC_INCIDENT_OBSERVER_URL", "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"]
)
def test_an_unconfigured_observer_fails_closed(
    tmp_path: Path,
    observer: Mock,
    capsys: pytest.CaptureFixture[str],
    missing: str,
) -> None:
    environ = _environ(tmp_path=tmp_path)
    del environ[missing]
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert "not configured" in capsys.readouterr().err
    assert observer.call_count == 0


@pytest.mark.parametrize("body", [None, "no block here"])
def test_a_pull_request_with_no_block_makes_no_request(
    tmp_path: Path, observer: Mock, capsys: pytest.CaptureFixture[str], body: str | None
) -> None:
    environ = _environ(tmp_path=tmp_path, body=body)
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert capsys.readouterr().err == ""
    assert observer.call_count == 0


@pytest.mark.parametrize("event_name", ["push", None])
def test_any_other_event_makes_no_request(
    tmp_path: Path, observer: Mock, event_name: str | None
) -> None:
    environ = _environ(tmp_path=tmp_path)
    environ.pop("GITHUB_EVENT_NAME")
    if event_name is not None:
        environ["GITHUB_EVENT_NAME"] = event_name
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert observer.call_count == 0


@pytest.mark.parametrize("contents", [None, "not json", "[]"])
def test_an_unreadable_event_makes_no_request(
    tmp_path: Path, observer: Mock, contents: str | None
) -> None:
    environ = _environ(tmp_path=tmp_path)
    path = Path(environ["GITHUB_EVENT_PATH"])
    if contents is None:
        path.unlink()
    else:
        path.write_text(contents, encoding="utf-8")
    assert not module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    assert observer.call_count == 0


def _commit(*, monkeypatch: pytest.MonkeyPatch, admitted: bool, message: str = _MESSAGE) -> Mock:
    monkeypatch.setattr(
        red_green_replay,
        "_git_stdout_lines",
        Mock(return_value=["livespec_dev_tooling/repair.py"]),
    )
    monkeypatch.setattr(
        red_green_replay,
        "_impl_prefixes_for_current_repo",
        Mock(return_value=("livespec_dev_tooling/",)),
    )
    monkeypatch.setattr(
        red_green_replay.subprocess,
        "run",
        Mock(return_value=SimpleNamespace(returncode=0, stdout=message, stderr="")),
    )
    monkeypatch.setattr(
        red_green_replay,
        "is_forge_authored_revert",
        Mock(return_value=IOSuccess(False)),  # noqa: FBT003
    )
    admission = Mock(return_value=admitted)
    monkeypatch.setattr(red_green_replay, "admitted_by_recorded_incident", admission, raising=False)
    return admission


def test_the_range_gate_clears_a_commit_the_incident_chain_records(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = _commit(monkeypatch=monkeypatch, admitted=True)
    assert red_green_replay._commit_violates(sha=_SHA) is False  # noqa: SLF001
    assert admission.call_args.kwargs["sha"] == _SHA
    assert admission.call_args.kwargs["message"] == _MESSAGE


def test_the_range_gate_keeps_convicting_a_commit_the_chain_does_not_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    admission = _commit(monkeypatch=monkeypatch, admitted=False)
    assert red_green_replay._commit_violates(sha=_SHA) is True  # noqa: SLF001
    assert admission.call_count == 1
