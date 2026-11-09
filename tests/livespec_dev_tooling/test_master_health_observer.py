"""The workflow-side transport fences every reconciler action behind the observer."""

from __future__ import annotations

import json

import pytest

from livespec_dev_tooling import master_health_observer as module
from livespec_dev_tooling.incident_ci_authority import OrdinaryActionOwnership

_ARGV = ["--repository", "owner/repo", "--head-sha", "b" * 40, "--run-id", "19"]
_ENV = {
    "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example/api",
    "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "controlled-query-token",
}


def observer(monkeypatch, *, answer):
    """Replace the hosted boundary; return what it was built with and asked."""
    seen = {}

    class Boundary:
        def __init__(self, *, observer_url, observer_token):
            seen["url"] = observer_url
            seen["token"] = observer_token

        def ordinary_action(self, *, query):
            seen["query"] = query
            return answer

    monkeypatch.setattr(module, "CiAuthorityBoundary", Boundary)
    return seen


@pytest.mark.parametrize(
    ("status", "reason"),
    [
        ("incident-owned", "independent incident controller owns repository action"),
        ("incident-owned", "pre-merge observer owns repository action"),
        ("ordinary", "ordinary reconciler policy retained"),
    ],
)
def test_the_observers_exact_answer_is_printed_for_the_workflow(
    monkeypatch, capsys, status, reason
):
    seen = observer(monkeypatch, answer=OrdinaryActionOwnership(status=status, reason=reason))

    assert module.main(argv=_ARGV, environ=_ENV) == 0

    assert json.loads(capsys.readouterr().out) == {"status": status, "reason": reason}
    assert seen == {
        "url": "https://observer.example/api",
        "token": "controlled-query-token",
        "query": {"repository": "owner/repo", "head_sha": "b" * 40, "run_id": 19},
    }


def test_a_repository_with_no_observer_keeps_its_existing_policy(monkeypatch, capsys):
    seen = observer(monkeypatch, answer=None)

    assert module.main(argv=_ARGV, environ={}) == 0

    assert json.loads(capsys.readouterr().out)["status"] == "ordinary"
    assert seen == {}


def test_an_unreadable_answer_names_its_cause_and_authorises_no_action(monkeypatch, capsys):
    observer(monkeypatch, answer=None)

    assert module.main(argv=_ARGV, environ=_ENV) == 1

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "observer.example" in captured.err
    assert "no readable ownership answer for run 19" in captured.err
    assert "no rerun, classification or revert action" in captured.err


def test_an_unparseable_observer_url_still_fails_closed_with_a_cause(monkeypatch, capsys):
    observer(monkeypatch, answer=None)

    assert module.main(argv=_ARGV, environ={"LIVESPEC_INCIDENT_OBSERVER_URL": "https://"}) == 1

    assert "an unparseable URL" in capsys.readouterr().err


def test_the_process_environment_is_the_default_source(monkeypatch, capsys):
    seen = observer(monkeypatch, answer=OrdinaryActionOwnership(status="ordinary", reason="r"))
    for name, value in _ENV.items():
        monkeypatch.setenv(name, value)

    assert module.main(argv=_ARGV) == 0

    assert seen["token"] == "controlled-query-token"
    assert json.loads(capsys.readouterr().out)["status"] == "ordinary"
