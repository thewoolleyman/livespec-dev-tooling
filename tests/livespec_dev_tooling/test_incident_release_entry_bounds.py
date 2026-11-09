"""The dispatch entrance bounds the reply, refuses an unusable configuration, and names every outcome."""

from __future__ import annotations

import http.client
import json
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_release_entry
from livespec_dev_tooling.incident_release_entry import ScreenRequest, screen

_SOURCE = "a" * 40
_QUERY = {"repository": "owner/repo", "source_sha": _SOURCE, "tag": "v1.2.3"}
_REQUEST = ScreenRequest(
    observed_repository="owner/repo", repository="owner/repo", source_sha=_SOURCE, tag="v1.2.3"
)
_CONFIGURED = {
    "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example.invalid:8765",
    "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "query-token",
}
_CLEAR = {"schema": 1, "status": "clear", "query": _QUERY}


def _observer(*, raw):
    response = Mock(status=http.client.ACCEPTED)
    response.read.return_value = raw
    connection = Mock()
    connection.getresponse.return_value = response
    return Mock(return_value=connection), response


def test_the_reply_is_read_with_a_bound_one_byte_past_the_limit():
    connect, response = _observer(raw=json.dumps(_CLEAR).encode())
    code, _line = screen(request=_REQUEST, environ=_CONFIGURED, connect=connect)
    assert code == 0
    response.read.assert_called_once_with(65537)


def test_a_reply_past_the_bound_is_refused_even_when_it_parses_as_clear():
    padded = b'{"schema": 1,' + b" " * 70000 + json.dumps(_CLEAR).encode()[len(b'{"schema": 1,') :]
    connect, _response = _observer(raw=padded)
    code, line = screen(request=_REQUEST, environ=_CONFIGURED, connect=connect)
    assert json.loads(padded) == _CLEAR
    assert code == 1
    assert line.startswith("incident-release-screen-malformed-reply:")


def test_a_url_that_already_names_the_screen_route_is_refused_without_a_call():
    connect, _response = _observer(raw=json.dumps(_CLEAR).encode())
    environ = {
        **_CONFIGURED,
        "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example.invalid/release/screen/",
    }
    code, line = screen(request=_REQUEST, environ=environ, connect=connect)
    assert (code, connect.call_count) == (1, 0)
    assert "is a base URL" in line


def test_a_configured_screen_with_no_observed_repository_refuses_rather_than_no_ops():
    connect, _response = _observer(raw=json.dumps(_CLEAR).encode())
    unnamed = ScreenRequest(
        observed_repository="", repository="owner/repo", source_sha=_SOURCE, tag="v1.2.3"
    )
    code, line = screen(request=unnamed, environ=_CONFIGURED, connect=connect)
    assert (code, connect.call_count) == (1, 0)
    assert line.startswith("incident-release-screen-misconfigured:")
    assert "no observed repository" in line


@pytest.mark.parametrize(
    ("environ", "request_", "reply", "expected"),
    [
        ({}, _REQUEST, _CLEAR, (0, "is unset")),
        (
            _CONFIGURED,
            ScreenRequest(
                observed_repository="owner/repo",
                repository="owner/sibling",
                source_sha=_SOURCE,
                tag="v1.2.3",
            ),
            _CLEAR,
            (0, "is not observed here"),
        ),
        (
            {**_CONFIGURED, "LIVESPEC_INCIDENT_OBSERVER_URL": "http://observer.example.invalid"},
            _REQUEST,
            _CLEAR,
            (1, "must be an https URL"),
        ),
        (_CONFIGURED, _REQUEST, b"not json", (1, "malformed-reply")),
        (
            _CONFIGURED,
            _REQUEST,
            {"status": "refused", "reason": "incident-release-recovery-retained"},
            (1, "incident-release-recovery-retained"),
        ),
        (_CONFIGURED, _REQUEST, {"status": "refused", "reason": ""}, (1, "malformed-reply")),
    ],
)
def test_every_other_outcome_keeps_its_exit_code_and_names_itself(
    environ, request_, reply, expected
):
    raw = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
    connect, _response = _observer(raw=raw)
    code, line = screen(request=request_, environ=environ, connect=connect)
    assert (code, expected[1] in line) == (expected[0], True)


def test_an_unreachable_observer_refuses_by_name():
    code, line = screen(
        request=_REQUEST, environ=_CONFIGURED, connect=Mock(side_effect=OSError("refused"))
    )
    assert code == 1
    assert line.startswith("incident-release-screen-unreachable:")


def test_main_writes_a_refusal_to_stderr_and_a_no_op_to_stdout(monkeypatch, capsys):
    argv = ["--observed-repository", "", "--repository", "owner/repo"]
    argv += ["--source-sha", _SOURCE, "--tag", "v1.2.3"]
    monkeypatch.setenv("LIVESPEC_INCIDENT_OBSERVER_URL", "https://observer.example.invalid")
    refused = incident_release_entry.main(argv=argv)
    refusal = capsys.readouterr()
    monkeypatch.delenv("LIVESPEC_INCIDENT_OBSERVER_URL")
    proceeded = incident_release_entry.main(argv=argv)
    proceed = capsys.readouterr()
    assert (refused, proceeded) == (1, 0)
    assert "no observed repository" in refusal.err
    assert "is unset" in proceed.out
