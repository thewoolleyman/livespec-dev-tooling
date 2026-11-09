"""The release dispatch entrance is a no-op without an observer and fails closed with one."""

from __future__ import annotations

import http.client
import json
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_release_entry
from livespec_dev_tooling.incident_release_entry import ScreenRequest, screen

_SOURCE = "a" * 40
_REQUEST = ScreenRequest(
    observed_repository="owner/repo", repository="owner/repo", source_sha=_SOURCE, tag="v1.2.3"
)
_CONFIGURED = {
    "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example.invalid:8765/base/",
    "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "query-token",
}
_QUERY = {"repository": "owner/repo", "source_sha": _SOURCE, "tag": "v1.2.3"}


def _observer(*, status, reply):
    raw = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
    response = Mock(status=status)
    response.read.return_value = raw
    connection = Mock()
    connection.getresponse.return_value = response
    return Mock(return_value=connection), connection


@pytest.mark.parametrize(
    ("request_", "environ", "expected"),
    [
        (_REQUEST, {}, "LIVESPEC_INCIDENT_OBSERVER_URL is unset"),
        (
            ScreenRequest(
                observed_repository="owner/repo",
                repository="owner/sibling",
                source_sha=_SOURCE,
                tag="v1.2.3",
            ),
            _CONFIGURED,
            "owner/sibling is not observed here (owner/repo)",
        ),
    ],
)
def test_a_dispatch_with_no_observer_for_its_source_proceeds_without_a_call(
    request_, environ, expected
):
    connect = Mock()
    code, line = screen(request=request_, environ=environ, connect=connect)
    assert (code, connect.call_count) == (0, 0)
    assert expected in line
    assert line.endswith("dispatch proceeds as normal")


@pytest.mark.parametrize(
    "environ",
    [
        {**_CONFIGURED, "LIVESPEC_INCIDENT_OBSERVER_URL": "http://observer.example.invalid"},
        {**_CONFIGURED, "LIVESPEC_INCIDENT_OBSERVER_URL": "https:///no-host"},
        {**_CONFIGURED, "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": ""},
    ],
)
def test_a_configured_but_unusable_observer_refuses_by_name(environ):
    connect = Mock()
    code, line = screen(request=_REQUEST, environ=environ, connect=connect)
    assert (code, connect.call_count) == (1, 0)
    assert line.startswith("incident-release-screen-misconfigured:")


def test_an_exact_clear_answer_lets_the_dispatch_proceed():
    connect, connection = _observer(
        status=http.client.ACCEPTED, reply={"schema": 1, "status": "clear", "query": _QUERY}
    )
    code, line = screen(request=_REQUEST, environ=_CONFIGURED, connect=connect)
    assert code == 0
    assert "v1.2.3 is clear" in line
    connect.assert_called_once_with("observer.example.invalid", port=8765, timeout=60)
    method, path = connection.request.call_args.args
    keywords = connection.request.call_args.kwargs
    assert (method, path) == ("POST", "/base/release/screen")
    assert json.loads(keywords["body"]) == _QUERY
    assert keywords["headers"]["Authorization"] == "Bearer query-token"
    assert connection.close.call_count == 1


@pytest.mark.parametrize(
    ("reply", "expected"),
    [
        (
            {
                "status": "refused",
                "reason": "incident-release-recovery-retained",
                "detail": "incident-release-recovery-retained: fenced by incident incident-1",
            },
            "incident-release-recovery-retained: fenced by incident incident-1",
        ),
        (
            {"status": "refused", "reason": "incident-release-source-unverifiable"},
            "incident-release-source-unverifiable",
        ),
    ],
)
def test_a_named_refusal_refuses_the_dispatch_by_that_name(reply, expected):
    connect, _connection = _observer(status=403, reply=reply)
    assert screen(request=_REQUEST, environ=_CONFIGURED, connect=connect) == (1, expected)


@pytest.mark.parametrize(
    ("status", "reply"),
    [
        (http.client.ACCEPTED, b"not json"),
        (http.client.ACCEPTED, ["clear"]),
        (http.client.ACCEPTED, {"schema": 1, "status": "clear", "query": {**_QUERY, "tag": "v9"}}),
        (403, {"schema": 1, "status": "clear", "query": _QUERY}),
        (403, {"status": "refused", "reason": ""}),
    ],
)
def test_an_inexact_reply_never_reads_as_clear(status, reply):
    connect, _connection = _observer(status=status, reply=reply)
    code, line = screen(request=_REQUEST, environ=_CONFIGURED, connect=connect)
    assert code == 1
    assert line == f"incident-release-screen-malformed-reply: HTTP {status} from the observer"


def test_an_unreachable_observer_refuses_and_closes_its_connection():
    refused = Mock(side_effect=OSError("connection refused"))
    connection = Mock()
    connection.getresponse.side_effect = http.client.RemoteDisconnected("gone")
    dropped = Mock(return_value=connection)
    outcomes = [
        screen(request=_REQUEST, environ=_CONFIGURED, connect=connect)
        for connect in (refused, dropped)
    ]
    assert [code for code, _line in outcomes] == [1, 1]
    assert all(line.startswith("incident-release-screen-unreachable:") for _code, line in outcomes)
    assert "observer.example.invalid" in outcomes[0][1]
    assert connection.close.call_count == 1


def test_main_proceeds_on_stdout_and_refuses_on_stderr(monkeypatch, capsys):
    argv = [
        "--observed-repository",
        "owner/repo",
        "--repository",
        "owner/repo",
        "--source-sha",
        _SOURCE,
        "--tag",
        "v1.2.3",
    ]
    monkeypatch.delenv("LIVESPEC_INCIDENT_OBSERVER_URL", raising=False)
    proceeded = incident_release_entry.main(argv=argv)
    proceed = capsys.readouterr()
    monkeypatch.setenv("LIVESPEC_INCIDENT_OBSERVER_URL", "http://observer.example.invalid")
    refused = incident_release_entry.main(argv=argv)
    refuse = capsys.readouterr()
    assert (proceeded, refused) == (0, 1)
    assert "dispatch proceeds as normal" in proceed.out
    assert refuse.err.startswith("incident-release-screen-misconfigured:")
