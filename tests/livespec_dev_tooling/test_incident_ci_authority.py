"""Hosted reads carry only a query token and require exact HTTPS replies."""

from __future__ import annotations

import http.client
import json
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_ci_authority as module


def query():
    return dict(
        repository="owner/repo",
        arm_id="d" * 64,
        pr_number=7,
        base_sha="a" * 40,
        head_sha="b" * 40,
        receipt_digest="e" * 64,
    )


def boundary(**changes):
    return module.CiAuthorityBoundary(
        **(
            dict(
                observer_url="https://controller.example/api",
                observer_token="controlled-query-token",  # noqa: S106 — public fixture token.
            )
            | changes
        )
    )


def wire(monkeypatch, *, raw=None, status=202, error=None):
    calls = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        if error:
            raise error

        def request(*args, **kwargs):
            calls.append((args, kwargs))

        response = SimpleNamespace(status=status, read=lambda _: raw)
        return SimpleNamespace(
            request=request, getresponse=lambda: response, close=lambda: calls.append("closed")
        )

    monkeypatch.setattr(module.http.client, "HTTPSConnection", connect)
    return calls


@pytest.mark.parametrize("route", ["current", "admitted"])
def test_exact_authenticated_route_reply_and_connection_cleanup(monkeypatch, route):
    calls = wire(monkeypatch, raw=json.dumps(dict(schema=1, status=route, query=query())).encode())
    assert getattr(boundary(), route)(query=query()) is True
    assert calls[1][0] == ("POST", "/api/" + route)
    assert json.loads(calls[1][1]["body"]) == query()
    assert calls[1][1]["headers"]["Authorization"] == "Bearer controlled-query-token"
    assert calls[-1] == "closed"


@pytest.mark.parametrize(
    "url",
    [
        "http://controller.example",
        "https://",
        "https://user@controller.example",
        "https://user:pass@controller.example",
        "https://controller.example?q=1",
        "https://controller.example#part",
        "https://controller.example:bad",
    ],
)
def test_invalid_urls_refuse_without_redirect_or_credentials(monkeypatch, url):
    calls = wire(monkeypatch, raw=b"{}")
    assert boundary(observer_url=url).current(query=query()) is False
    assert calls == []


@pytest.mark.parametrize(
    "token", ["", " leading", "trailing ", "embedded\nnewline", "embedded space", "x" * 4097]
)
def test_invalid_tokens_are_never_sent(monkeypatch, token):
    calls = wire(monkeypatch, raw=b"{}")
    assert boundary(observer_token=token).current(query=query()) is False
    assert calls == []


@pytest.mark.parametrize(
    "change",
    [
        {"extra": "x"},
        {"pr_number": True},
        {"pr_number": 0},
        {"arm_id": 1},
        {"repository": "/foreign"},
        {"arm_id": "x"},
        {"receipt_digest": "x"},
        {"base_sha": "x"},
        {"head_sha": "x"},
    ],
)
def test_invalid_query_is_not_transmitted(monkeypatch, change):
    calls = wire(monkeypatch, raw=b"{}")
    assert boundary().current(query=query() | change) is False
    assert calls == []


@pytest.mark.parametrize(
    "reply",
    [
        [],
        {},
        dict(schema=True, status="current", query=query()),
        dict(schema=2, status="current", query=query()),
        dict(schema=1, status="admitted", query=query()),
        dict(schema=1, status="current", query=query() | {"pr_number": True}),
        dict(schema=1, status="current", query=query(), extra="x"),
    ],
)
def test_wrong_reply_kinds_cannot_authorize_current(monkeypatch, reply):
    wire(monkeypatch, raw=json.dumps(reply).encode())
    assert boundary().current(query=query()) is False


@pytest.mark.parametrize(
    ("raw", "status"),
    [
        (b"{}", 302),
        (b"x" * 65537, 202),
        (b"{bad", 202),
        (b'{"schema":1,"schema":1}', 202),
        (b"\xff", 202),
    ],
)
def test_redirect_oversize_and_malformed_replies_fail_closed(monkeypatch, raw, status):
    wire(monkeypatch, raw=raw, status=status)
    assert boundary().current(query=query()) is False


@pytest.mark.parametrize("error", [OSError("offline"), http.client.HTTPException("bad protocol")])
def test_network_and_protocol_failure_is_refusal(monkeypatch, error):
    wire(monkeypatch, error=error)
    assert boundary().current(query=query()) is False
