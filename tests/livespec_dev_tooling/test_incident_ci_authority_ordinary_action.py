"""The hosted reconciler reads the observer's exact ownership answer or names why not.

Review findings F6 and F7 on livespec-dev-tooling#3915: client-side refusals
were silent, a reply whose status was a list raised an unhandled TypeError, and
the non-202, oversize and exact-key-set guards had no test that failed without
them (livespec-dev-tooling-ariayn).
"""

from __future__ import annotations

import http.client
import json
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_ci_authority as module

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_PREFIX = "incident-ci: observer read refused: "
_WHERE = " while reading /ordinary-action from controller.example:443 as controller.example"


def _query(**changes):
    return {
        "repository": "owner/repo",
        "action": "open-revert",
        "window_shas": ["a" * 40],
    } | changes


def _boundary(**changes):
    return module.CiAuthorityBoundary(
        **(
            {
                "observer_url": "https://controller.example/api",
                "observer_token": "controlled-query-token",
            }
            | changes
        )
    )


def _reply(**changes):
    reply = {
        "schema": 1,
        "status": "incident-owned",
        "reason": "independent incident controller owns repository action",
        "receipt": None,
        "query": _query(),
    }
    reply.update(changes)
    return json.dumps(reply).encode()


def _wire(monkeypatch, *, raw=b"", status=202, error=None):
    calls = []

    def connect(*args, **kwargs):
        calls.append((args, kwargs))
        if error:
            raise error
        response = SimpleNamespace(status=status, read=lambda _limit: raw)
        return SimpleNamespace(
            request=lambda *a, **k: calls.append((a, k)),
            getresponse=lambda: response,
            close=lambda: calls.append("closed"),
        )

    monkeypatch.setattr(module.http.client, "HTTPSConnection", connect)
    monkeypatch.delenv("LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR", raising=False)
    return calls


def test_an_exact_incident_owned_answer_is_read_from_the_query_route(monkeypatch):
    calls = _wire(monkeypatch, raw=_reply())

    answer = _boundary().ordinary_action(query=_query())

    assert answer == module.OrdinaryActionOwnership(
        status="incident-owned",
        reason="independent incident controller owns repository action",
        receipt=None,
    )
    assert calls[0][1]["timeout"] == 60
    assert calls[1][0] == ("POST", "/api/ordinary-action")
    assert json.loads(calls[1][1]["body"]) == _query()
    assert calls[1][1]["headers"]["Authorization"] == "Bearer controlled-query-token"
    assert calls[-1] == "closed"


def test_an_exact_ordinary_answer_carries_the_observer_receipt(monkeypatch):
    receipt = "ordinary open-revert retained by the master-health reconciler"
    _ = _wire(
        monkeypatch,
        raw=_reply(
            status="ordinary", reason="ordinary reconciler policy retained", receipt=receipt
        ),
    )

    answer = _boundary().ordinary_action(query=_query())

    assert (answer.status, answer.receipt) == ("ordinary", receipt)


@pytest.mark.parametrize(
    ("changes", "cause"),
    [
        (
            {"observer_url": "http://controller.example"},
            "the observer URL is not an https URL with a host and no credentials, query or fragment",
        ),
        (
            {"observer_url": "https://controller.example:bad"},
            "the observer URL is not an https URL with a host and no credentials, query or fragment",
        ),
        (
            {"observer_url": "https://user@controller.example"},
            "the observer URL is not an https URL with a host and no credentials, query or fragment",
        ),
        (
            {"observer_token": ""},
            "the observer query token is empty, oversize or not a valid header value",
        ),
    ],
)
def test_a_bad_url_or_token_is_named_and_nothing_is_dialed(monkeypatch, capsys, changes, cause):
    """F6: these refusals used to return silently."""
    calls = _wire(monkeypatch, raw=_reply())

    answer = _boundary(**changes).ordinary_action(query=_query())

    assert (answer.status, answer.reason) == (
        module.UNREADABLE,
        cause + "; no connection was attempted",
    )
    assert capsys.readouterr().err == _PREFIX + cause + "; no connection was attempted\n"
    assert calls == []


@pytest.mark.parametrize(
    "query",
    [
        _query(window_shas=["A" * 40]),
        _query(window_shas="a" * 40),
        _query(window_shas=["a" * 40] * 129),
        _query(action=""),
        _query(action=["open-revert"]),
        _query(repository="not a repository"),
        _query(repository=7),
        _query(extra=True),
    ],
)
def test_a_malformed_query_is_named_and_never_sent(monkeypatch, query):
    calls = _wire(monkeypatch, raw=_reply())

    answer = _boundary().ordinary_action(query=query)

    assert (answer.status, answer.reason) == (
        module.UNREADABLE,
        "the ordinary-action query is malformed; no connection was attempted",
    )
    assert calls == []


def test_an_invalid_connect_address_is_named_and_nothing_is_dialed(monkeypatch):
    calls = _wire(monkeypatch, raw=_reply())
    monkeypatch.setenv("LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR", "vps.example")

    answer = _boundary().ordinary_action(query=_query())

    assert answer.status == module.UNREADABLE
    assert answer.reason == (
        "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR is not an IPv4 or IPv6 address literal;"
        " no connection was attempted"
    )
    assert calls == []


@pytest.mark.parametrize(
    "error", [OSError("refused"), TimeoutError("slow"), http.client.RemoteDisconnected("gone")]
)
def test_a_transport_failure_is_named_with_its_class_and_route(monkeypatch, error):
    _ = _wire(monkeypatch, error=error)

    answer = _boundary(observer_url="https://controller.example").ordinary_action(query=_query())

    assert (answer.status, answer.reason) == (module.UNREADABLE, type(error).__name__ + _WHERE)


@pytest.mark.parametrize(
    ("status", "raw", "cause"),
    [
        # F7: a valid body behind a non-202 status is still refused.
        (200, _reply(), "HTTP 200"),
        (403, _reply(), "HTTP 403"),
        # F7: an otherwise exact reply past the bound is refused, not parsed.
        (202, _reply(reason="x" * 65536), "oversize reply"),
        (202, b"not json", "unparseable reply"),
        (202, b"\xff\xfe", "unparseable reply"),
        (202, b"[]", "reply is not the exact ordinary-action answer"),
        # F7: an extra key is refused.
        (202, _reply(extra=1), "reply is not the exact ordinary-action answer"),
        # F6: a list status no longer raises TypeError.
        (202, _reply(status=["ordinary"]), "reply is not the exact ordinary-action answer"),
        (202, _reply(status="refused"), "reply is not the exact ordinary-action answer"),
        (202, _reply(schema=True), "reply is not the exact ordinary-action answer"),
        (202, _reply(schema=2), "reply is not the exact ordinary-action answer"),
        (202, _reply(reason=""), "reply is not the exact ordinary-action answer"),
        (202, _reply(reason=["x"]), "reply is not the exact ordinary-action answer"),
        (202, _reply(receipt="stray"), "reply is not the exact ordinary-action answer"),
        (
            202,
            _reply(status="ordinary", receipt=None),
            "reply is not the exact ordinary-action answer",
        ),
        (
            202,
            _reply(status="ordinary", receipt=""),
            "reply is not the exact ordinary-action answer",
        ),
        (
            202,
            _reply(query=_query(window_shas=[])),
            "reply is not the exact ordinary-action answer",
        ),
    ],
)
def test_anything_but_the_exact_bounded_202_reply_is_unreadable(
    monkeypatch, capsys, status, raw, cause
):
    _ = _wire(monkeypatch, raw=raw, status=status)

    answer = _boundary(observer_url="https://controller.example").ordinary_action(query=_query())

    assert (answer.status, answer.reason, answer.receipt) == (
        module.UNREADABLE,
        cause + _WHERE,
        None,
    )
    assert capsys.readouterr().err == _PREFIX + cause + _WHERE + "\n"
