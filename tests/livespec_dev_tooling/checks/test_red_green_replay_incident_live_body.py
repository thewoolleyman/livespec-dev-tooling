"""A label re-run reads the pull request body live, not the stale event payload."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import Mock

from livespec_dev_tooling.checks import _red_green_replay_incident as module
from tests.livespec_dev_tooling.checks.test_red_green_replay_incident import (
    _BASE,
    _HEAD,
    _MESSAGE,
    _SHA,
    _body,
    _environ,
    observer,  # noqa: F401  — pytest fixture imported from the sibling module
)

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
__all__: list[str] = []

_READ = "red-green-replay-pull-request-body-read"


def test_a_live_pull_request_body_admits_a_label_rerun_with_a_stale_event_payload(
    tmp_path: Path,
    observer: Mock,  # noqa: F811  — the imported fixture
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environ = _environ(tmp_path=tmp_path, body="before the incident block") | {
        "GITHUB_REPOSITORY": "owner/repo"
    }
    live = {"number": 7, "base": {"sha": _BASE}, "head": {"sha": _HEAD}, "body": _body()}
    forge_read = Mock(
        return_value=SimpleNamespace(outcome="answer", body=json.dumps(live), lines=())
    )
    monkeypatch.setattr(module, "forge_call", forge_read, raising=False)

    admitted = module.admitted_by_recorded_incident(sha=_SHA, message=_MESSAGE, environ=environ)

    assert admitted is True
    assert forge_read.call_args.kwargs == {"name": _READ, "endpoint": "repos/owner/repo/pulls/7"}
    assert observer.call_count == 1


def test_an_unanswered_live_pull_request_read_names_its_retry_and_is_not_used(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    environ = _environ(tmp_path=tmp_path) | {"GITHUB_REPOSITORY": "owner/repo"}
    forge_read = Mock(
        return_value=SimpleNamespace(outcome="failed", body="", lines=("forge-read: retrying",))
    )
    monkeypatch.setattr(module, "forge_call", forge_read, raising=False)

    pull_request = module._pull_request(environ=environ)  # noqa: SLF001

    assert pull_request == {}
    assert capsys.readouterr().err == "forge-read: retrying\n"
    assert forge_read.call_args.kwargs == {"name": _READ, "endpoint": "repos/owner/repo/pulls/7"}
