"""Fresh forge events authenticate PR labels and exact head before incident reads."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_ci_event as module


def environment():
    return dict(
        GITHUB_EVENT_NAME="pull_request",
        GITHUB_REPOSITORY="owner/repo",
        GITHUB_PR_NUMBER="7",
        GITHUB_PR_HEAD_SHA="b" * 40,
    )


def pr():
    return dict(
        number=7,
        state="open",
        head=dict(sha="b" * 40, repo=dict(full_name="owner/repo")),
        base=dict(sha="a" * 40, repo=dict(full_name="owner/repo")),
        labels=[dict(name="expedited-incident-response")],
        body="<!-- livespec-incident-ci\n{}\n-->",
    )


def wire(monkeypatch, *, data=None, code=0, raw=None):
    def read(**kwargs):
        assert kwargs["args"] == ["api", "repos/owner/repo/pulls/7"]
        return subprocess.CompletedProcess(
            [], code, json.dumps(pr() if data is None else data) if raw is None else raw, ""
        )

    monkeypatch.setattr(module, "gh_read", read)


def test_normal_master_never_reads_forge_or_incident_payload(monkeypatch):
    forbidden = Mock(side_effect=AssertionError("read forbidden"))
    monkeypatch.setattr(module, "gh_read", forbidden)
    value = module.observe_event(
        environ=dict(GITHUB_EVENT_NAME="push", GITHUB_REPOSITORY="owner/repo", GITHUB_SHA="b" * 40)
    )
    assert value is not None and value[0].kind == "push" and value[1] == ""
    assert module.observe_event(environ={}) is None
    for change in (
        {"GITHUB_REPOSITORY": "bad"},
        {"GITHUB_SHA": "bad"},
        {"GITHUB_BEFORE_SHA": "bad"},
        {"GITHUB_EVENT_NAME": "workflow_dispatch"},
    ):
        assert (
            module.observe_event(
                environ=dict(
                    GITHUB_EVENT_NAME="push", GITHUB_REPOSITORY="owner/repo", GITHUB_SHA="b" * 40
                )
                | change
            )
            is None
        )
    assert forbidden.call_count == 0


def test_current_incident_and_ordinary_pr_projection(monkeypatch):
    wire(monkeypatch)
    result = module.observe_event(environ=environment())
    assert result is not None and result[0].pr_number == 7 and result[1] == "{}"
    wire(monkeypatch, data=pr() | {"labels": [], "body": None})
    ordinary = module.observe_event(environ=environment())
    assert ordinary is not None and ordinary[1] == ""


@pytest.mark.parametrize(
    "change",
    [
        {"state": "closed"},
        {"number": True},
        {"number": 8},
        {"head": {}},
        {"base": {}},
        {"head": {"sha": "bad"}},
        {"base": {"sha": "bad"}},
        {"base": {"sha": "a" * 40, "repo": {"full_name": "foreign/repo"}}},
        {"labels": {}},
        {"labels": [None]},
        {"labels": [{"name": 1}]},
        {"labels": [{"name": "x"}, {"name": "x"}]},
    ],
)
def test_stale_foreign_or_malformed_forge_records_refuse(monkeypatch, change):
    wire(monkeypatch, data=pr() | change)
    assert module.observe_event(environ=environment()) is None


@pytest.mark.parametrize(
    "body",
    [
        None,
        "missing",
        "<!-- livespec-incident-ci\n{}\n-->\n-->",
        "<!-- livespec-incident-ci\n" + "x" * 16385 + "\n-->",
    ],
)
def test_missing_duplicate_and_oversize_packet_refuse(monkeypatch, body):
    wire(monkeypatch, data=pr() | {"body": body})
    assert module.observe_event(environ=environment()) is None


def test_fork_incident_and_failed_or_duplicate_forge_reply_refuse(monkeypatch):
    wire(monkeypatch, data=pr() | {"head": {"sha": "b" * 40, "repo": {"full_name": "fork/repo"}}})
    assert module.observe_event(environ=environment()) is None
    wire(monkeypatch, code=1)
    assert module.observe_event(environ=environment()) is None
    wire(monkeypatch, raw='{"number":7,"number":7}')
    assert module.observe_event(environ=environment()) is None
    wire(monkeypatch, data=[])
    assert module.observe_event(environ=environment()) is None
    assert module.observe_event(environ=environment() | {"GITHUB_PR_NUMBER": "0"}) is None
