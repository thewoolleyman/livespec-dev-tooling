"""A replay gate that finds no incident block says so, naming the source it read.

Scenario "incident commit provenance remains verifiable on normal master": when
the pull request carries no livespec-incident-ci block, the replay gate MUST print
a line naming the missing block and the source it read, and keep the commit
convicted (livespec-dev-tooling-yfrepg).
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_ci_authority
from livespec_dev_tooling.checks import _red_green_replay_incident as module

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
_SHA = "c" * 40
_MESSAGE = "fix: repair\n\nFactory-Override: EXPEDITED_INCIDENT_RESPONSE flag: item\n"


def _environ(*, tmp_path: Path, event_name: str, payload: object) -> dict[str, str]:
    event = tmp_path / "event.json"
    event.write_text(json.dumps(payload), encoding="utf-8")
    return {
        "GITHUB_EVENT_NAME": event_name,
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
    return answer


@pytest.mark.parametrize("body", [None, "no block here"])
def test_a_pull_request_without_a_block_names_the_missing_block_and_the_body_it_read(
    tmp_path: Path, observer: Mock, capsys: pytest.CaptureFixture[str], body: str | None
) -> None:
    pull_request = {
        "number": 7,
        "body": body,
        "base": {"sha": "a" * 40},
        "head": {"sha": "b" * 40},
    }
    environ = _environ(
        tmp_path=tmp_path, event_name="pull_request", payload={"pull_request": pull_request}
    )
    admitted = module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    err = capsys.readouterr().err
    facts = [
        not admitted,
        "incident-provenance-refused: " + _SHA + ": " in err,
        "no livespec-incident-ci block" in err,
        "pull_request body" in err,
        observer.call_count == 0,
    ]
    assert all(facts), err


def test_a_merge_group_run_names_the_missing_block_and_that_it_read_no_pull_request(
    tmp_path: Path, observer: Mock, capsys: pytest.CaptureFixture[str]
) -> None:
    merge_group = {"head_ref": "refs/heads/gh-readonly-queue/master/pr-7-" + "a" * 40}
    environ = _environ(
        tmp_path=tmp_path, event_name="merge_group", payload={"merge_group": merge_group}
    )
    admitted = module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)
    err = capsys.readouterr().err
    facts = [
        not admitted,
        "incident-provenance-refused: " + _SHA + ": " in err,
        "no livespec-incident-ci block" in err,
        "merge_group" in err,
        observer.call_count == 0,
    ]
    assert all(facts), err
