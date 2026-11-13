"""The publisher posts a PASSED aggregate and names every answer it does not accept."""

from __future__ import annotations

import http.client
import json
from typing import ClassVar

import pytest

from livespec_dev_tooling import incident_ci_publish as publish_module
from livespec_dev_tooling.incident_ci_publish import (
    main,
    publication_query,
    publish,
    request_identity_token,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_QUERY = {
    "repository": "owner/repo",
    "arm_id": "a" * 64,
    "pr_number": 55,
    "base_sha": "b" * 40,
    "head_sha": "c" * 40,
    "receipt_digest": "d" * 64,
}
_JWT = "jwt"
_AGGREGATE = {"status": "passed", "head_sha": "c" * 40, "passed": ["check-lint"]}
_ENVIRON = {
    "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example:8443/base/",
    "ACTIONS_ID_TOKEN_REQUEST_URL": "https://token.example/request?api-version=2.0",
    "ACTIONS_ID_TOKEN_REQUEST_TOKEN": "request-bearer",
}


def replying(status, reply, sent):
    def send(*, url, token, body, connect_to):
        sent.append({"url": url, "token": token, "body": json.loads(body), "to": connect_to})
        raw = reply if isinstance(reply, bytes) else json.dumps(reply).encode()
        return status, raw

    return send


def run(reply, *, status=202, environ=None, aggregate=None, sent=None):
    sent = [] if sent is None else sent
    return publish(
        environ=_ENVIRON if environ is None else environ,
        release="v1.2.3",
        aggregate=json.dumps(_AGGREGATE if aggregate is None else aggregate),
        query=json.dumps(_QUERY),
        send=replying(status, reply, sent),
        token_source=lambda **_: "oidc-jwt",
    )


@pytest.mark.parametrize("answered", ["published", "retained"])
def test_an_accepted_publication_exits_zero(answered):
    sent = []
    code, text = run({"status": answered, "aggregate_digest": "e" * 64}, sent=sent)
    assert code == 0 and answered in text and "e" * 64 in text
    [request] = sent
    assert request == {
        "url": _ENVIRON["LIVESPEC_INCIDENT_OBSERVER_URL"],
        "token": "oidc-jwt",
        "body": {"query": _QUERY, "aggregate": _AGGREGATE, "release": "v1.2.3"},
        "to": None,
    }


def test_identity_not_provisioned_does_not_fail_the_job():
    code, text = run({"status": "refused", "reason": "identity-not-provisioned"}, status=403)
    assert code == 0 and "identity-not-provisioned" in text


@pytest.mark.parametrize(
    ("status", "reply", "named"),
    [
        (403, {"status": "refused", "reason": "publication-stale"}, "publication-stale"),
        (409, {"status": "conflict", "aggregate_digest": "e" * 64}, "conflict"),
        (403, ["not", "an", "object"], "HTTP 403"),
        (502, b"<html>bad gateway</html>", "unreadable"),
    ],
)
def test_every_other_answer_fails_the_job_naming_it(status, reply, named):
    code, text = run(reply, status=status)
    assert code == 1 and named in text


def test_an_unpassed_aggregate_is_never_published():
    sent = []
    code, text = run({"status": "published"}, aggregate={"status": "failed"}, sent=sent)
    assert (code, sent) == (1, []) and "did not pass" in text


@pytest.mark.parametrize(
    "environ",
    [
        {k: v for k, v in _ENVIRON.items() if k != "LIVESPEC_INCIDENT_OBSERVER_URL"},
        _ENVIRON | {"LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR": "not-an-address"},
    ],
)
def test_missing_configuration_fails_the_job(environ):
    code, text = run({"status": "published"}, environ=environ)
    assert code == 1 and "could not be reached" in text


def test_a_connect_address_literal_is_passed_to_the_sender():
    sent = []
    environ = _ENVIRON | {"LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR": "100.64.0.1"}
    assert run({"status": "published"}, environ=environ, sent=sent)[0] == 0
    assert sent[0]["to"] == "100.64.0.1"


class _Response:
    def __init__(self, raw):
        self.raw = raw
        self.status = 202

    def read(self, limit):
        return self.raw[:limit]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_the_identity_token_is_requested_for_the_configured_audience(monkeypatch):
    seen = []

    def urlopen(request, timeout):
        seen.append((request.full_url, request.get_header("Authorization"), timeout))
        return _Response(json.dumps({"value": "oidc-jwt"}).encode())

    monkeypatch.setattr(publish_module.urllib.request, "urlopen", urlopen)
    environ = _ENVIRON | {"LIVESPEC_INCIDENT_CI_AUDIENCE": "urn:livespec controller"}
    assert request_identity_token(environ=environ) == "oidc-jwt"
    assert request_identity_token(environ=_ENVIRON) == "oidc-jwt"
    assert [url for url, *_ in seen] == [
        _ENVIRON["ACTIONS_ID_TOKEN_REQUEST_URL"] + "&audience=urn%3Alivespec%20controller",
        _ENVIRON["ACTIONS_ID_TOKEN_REQUEST_URL"],
    ]
    assert {header for _, header, _ in seen} == {"bearer request-bearer"}


@pytest.mark.parametrize(
    ("environ", "raw"),
    [
        (_ENVIRON | {"ACTIONS_ID_TOKEN_REQUEST_URL": "http://token.example/r?x=1"}, b"{}"),
        (_ENVIRON, b'{"value": ""}'),
        (_ENVIRON, b"[]"),
    ],
)
def test_an_unusable_identity_token_response_raises(monkeypatch, environ, raw):
    monkeypatch.setattr(publish_module.urllib.request, "urlopen", lambda *_, **__: _Response(raw))
    with pytest.raises(ValueError, match="identity token"):
        _ = request_identity_token(environ=environ)


class _Connection:
    made: ClassVar[list] = []

    def __init__(self, host, port, timeout):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock = None
        self.requests = []
        _Connection.made.append(self)

    def request(self, method, path, body, headers):
        self.requests.append((method, path, body, headers))

    def getresponse(self):
        return _Response(b'{"status": "published"}')

    def close(self):
        self.closed = True


class _Context:
    def wrap_socket(self, raw, server_hostname):
        return ("wrapped", raw, server_hostname)


@pytest.mark.parametrize("connect_to", [None, "100.64.0.1"])
def test_the_sender_posts_to_the_publish_route(monkeypatch, connect_to):
    _Connection.made = []
    monkeypatch.setattr(publish_module.http.client, "HTTPSConnection", _Connection)
    monkeypatch.setattr(
        publish_module.socket, "create_connection", lambda address, **_: ("raw", address)
    )
    monkeypatch.setattr(publish_module.ssl, "create_default_context", _Context)
    status, raw = publish_module.send_publication(
        url="https://observer.example:8443/base/", token=_JWT, body=b"{}", connect_to=connect_to
    )
    assert (status, raw) == (202, b'{"status": "published"}')
    [connection] = _Connection.made
    assert (connection.host, connection.port, connection.closed) == ("observer.example", 8443, True)
    [(method, path, body, headers)] = connection.requests
    assert (method, path, body) == ("POST", "/base/ci/publish", b"{}")
    assert headers["Authorization"] == "Bearer jwt"
    if connect_to is None:
        assert connection.sock is None
    else:
        assert connection.sock == ("wrapped", ("raw", (connect_to, 8443)), "observer.example")


@pytest.mark.parametrize(
    "url", ["http://observer.example/", "https:///path", "https://observer.example/?q=1"]
)
def test_the_sender_refuses_a_url_that_is_not_plain_https(url):
    with pytest.raises(ValueError, match="https"):
        _ = publish_module.send_publication(url=url, token=_JWT, body=b"{}", connect_to=None)


def test_the_sender_defaults_to_the_https_port(monkeypatch):
    _Connection.made = []
    monkeypatch.setattr(publish_module.http.client, "HTTPSConnection", _Connection)
    _ = publish_module.send_publication(
        url="https://observer.example", token=_JWT, body=b"{}", connect_to=None
    )
    assert _Connection.made[0].port == http.client.HTTPS_PORT


def test_the_query_comes_from_the_incident_block(monkeypatch):
    authority = object()
    monkeypatch.setattr(publish_module, "observe_event", lambda **_: ("event", "payload"))
    monkeypatch.setattr(
        publish_module,
        "decode_authority",
        lambda payload: authority if payload == "payload" else None,
    )
    monkeypatch.setattr(
        publish_module, "query_for", lambda authority: _QUERY if authority is not None else None
    )
    assert publication_query(environ={}) == _QUERY
    monkeypatch.setattr(publish_module, "decode_authority", lambda **_: None)
    assert publication_query(environ={}) is None
    monkeypatch.setattr(publish_module, "observe_event", lambda **_: None)
    assert publication_query(environ={}) is None


def test_main_query_writes_the_job_output(monkeypatch, tmp_path, capsys):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(publish_module, "publication_query", lambda **_: _QUERY)
    assert main(argv=["query"]) == 0
    line = json.dumps(_QUERY, sort_keys=True)
    assert output.read_text() == "query=" + line + "\n"
    assert capsys.readouterr().out == line + "\n"
    monkeypatch.setattr(publish_module, "publication_query", lambda **_: None)
    assert main(argv=["query"]) == 2
    assert "no retained arm query" in capsys.readouterr().out


@pytest.mark.parametrize(("code", "prefix"), [(0, "::notice::"), (1, "::error::")])
def test_main_publish_reports_to_the_log_and_step_summary(
    monkeypatch, tmp_path, capsys, code, prefix
):
    summary = tmp_path / "summary"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    monkeypatch.setenv("INCIDENT_CI_RELEASE", "v1.2.3")
    monkeypatch.setenv("INCIDENT_CI_AGGREGATE", "{}")
    monkeypatch.setenv("INCIDENT_CI_QUERY", "{}")
    calls = []

    def fake(**kwargs):
        calls.append(kwargs)
        return code, "the answer"

    monkeypatch.setattr(publish_module, "publish", fake)
    assert main(argv=["publish"]) == code
    assert calls[0]["release"] == "v1.2.3"
    assert capsys.readouterr().out == prefix + "incident-ci-publish: the answer\n"
    assert summary.read_text() == "## incident-ci-publish\n\nthe answer.\n"


def test_main_publish_without_a_summary_file_still_reports(monkeypatch, capsys):
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(publish_module, "publish", lambda **_: (0, "ok"))
    assert main(argv=["publish"]) == 0
    assert "ok" in capsys.readouterr().out
