"""A refused observer read names its cause; the connect-address override keeps its shape.

livespec-dev-tooling-ws2idp. The drill on 2026-11-06 measured the incident-ci job
refusing twice after 123 s each with "fresh current authority and independent admission
required" and nothing else: every `/current` and `/admitted` read from the k3s runner
pod had hung to the client ceiling against Tailscale's public Funnel ingress, and the
client's handler turned each error into a silent False. The connect-address override
(`LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR`, master 04b8ef8c) fixed the reach; this
module holds the third condition of that fix: a refusal caused by a connection, TLS or
socket error names the error class, the route and the host:port it tried on stderr,
never the token, and an invalid override literal refuses by the variable's name without
connecting. The override's own shape is asserted here too, from the paired test's
side, so the per-file gate measures this module against the client.
"""

from __future__ import annotations

import http.client
import json
import ssl
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_ci_authority as module

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ws2idp
_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR"
_URL = "https://controller.example:8765/api"
_HOST = "controller.example"
_ADDRESS = "100.89.189.118"
_CEILING = 630


def _query() -> dict[str, object]:
    return {
        "repository": "owner/repo",
        "arm_id": "d" * 64,
        "pr_number": 7,
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "receipt_digest": "e" * 64,
    }


def _boundary(*, url: str = _URL) -> module.CiAuthorityBoundary:
    return module.CiAuthorityBoundary(
        observer_url=url,
        observer_token="controlled-query-token",  # noqa: S106 — public fixture token.
    )


def _wire(
    *, monkeypatch, route: str = "current", dial_error=None, tls_error=None, connect_error=None
) -> dict[str, list[object]]:
    """Capture every socket, TLS and HTTP step the client takes."""
    seen: dict[str, list[object]] = {"connections": [], "tcp": [], "tls": [], "requests": []}
    raw = json.dumps({"schema": 1, "status": route, "query": _query()}).encode()

    class _Connection:
        def __init__(self, host, port=None, timeout=None, **kwargs):
            seen["connections"].append({"host": host, "port": port, "timeout": timeout, **kwargs})
            self.host = host
            self.sock = None

        def request(self, method, path, body=None, headers=None):  # noqa: ARG002 — the client passes body by keyword.
            if connect_error is not None:
                raise connect_error
            seen["requests"].append(
                {"method": method, "path": path, "headers": dict(headers or {}), "sock": self.sock}
            )

        def getresponse(self):
            return SimpleNamespace(status=202, read=lambda _: raw)

        def close(self):
            return None

    def create_connection(address, timeout=None, **_kwargs):
        seen["tcp"].append({"address": address, "timeout": timeout})
        if dial_error is not None:
            raise dial_error
        return SimpleNamespace(kind="tcp", address=address, close=lambda: None)

    class _Context:
        def wrap_socket(self, sock, server_hostname=None, **_kwargs):
            seen["tls"].append({"sock": sock, "server_hostname": server_hostname})
            if tls_error is not None:
                raise tls_error
            return SimpleNamespace(kind="tls", inner=sock, server_hostname=server_hostname)

    monkeypatch.setattr(module.http.client, "HTTPSConnection", _Connection)
    monkeypatch.setattr(
        module, "socket", SimpleNamespace(create_connection=create_connection), raising=False
    )
    monkeypatch.setattr(
        module, "ssl", SimpleNamespace(create_default_context=lambda: _Context()), raising=False
    )
    return seen


@pytest.mark.parametrize("route", ["current", "admitted"])
def test_an_override_address_is_dialed_while_the_url_host_is_verified_and_sent(
    monkeypatch, capsys, route
) -> None:
    seen = _wire(monkeypatch=monkeypatch, route=route)
    monkeypatch.setenv(_VARIABLE, _ADDRESS)

    assert getattr(_boundary(), route)(query=_query()) is True
    assert seen["tcp"] == [{"address": (_ADDRESS, 8765), "timeout": _CEILING}]
    assert [t["server_hostname"] for t in seen["tls"]] == [_HOST]
    assert seen["tls"][0]["sock"].kind == "tcp"
    assert [(c["host"], c["port"], c["timeout"]) for c in seen["connections"]] == [
        (_HOST, 8765, _CEILING)
    ]
    assert seen["requests"][0]["sock"].kind == "tls"
    assert seen["requests"][0]["sock"].inner.kind == "tcp"
    assert seen["requests"][0]["path"] == "/api/" + route
    assert seen["requests"][0]["headers"].get("Host", _HOST) == _HOST
    assert capsys.readouterr().err == ""


def test_an_ipv6_override_literal_is_dialed_the_same_way_and_a_bare_url_uses_443(
    monkeypatch,
) -> None:
    seen = _wire(monkeypatch=monkeypatch)
    monkeypatch.setenv(_VARIABLE, "fd7a:115c:a1e0::5f01:bd8d")

    assert _boundary(url="https://controller.example/api").current(query=_query()) is True
    assert seen["tcp"] == [{"address": ("fd7a:115c:a1e0::5f01:bd8d", 443), "timeout": _CEILING}]
    assert [t["server_hostname"] for t in seen["tls"]] == [_HOST]
    assert [(c["host"], c["port"]) for c in seen["connections"]] == [(_HOST, None)]


def test_without_the_variable_the_client_connects_by_hostname_as_before(
    monkeypatch, capsys
) -> None:
    seen = _wire(monkeypatch=monkeypatch)
    monkeypatch.delenv(_VARIABLE, raising=False)

    assert _boundary().current(query=_query()) is True
    assert seen["tcp"] == []
    assert seen["tls"] == []
    assert [(c["host"], c["port"], c["timeout"]) for c in seen["connections"]] == [
        (_HOST, 8765, _CEILING)
    ]
    assert seen["requests"][0]["sock"] is None
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize(
    "value",
    [
        "vps.perch-rudd.ts.net",
        "100.89.189",
        " 100.89.189.118",
        "100.89.189.118:8765",
        "[fd7a:115c:a1e0::5f01:bd8d]",
        "https://100.89.189.118",
    ],
)
def test_an_invalid_override_literal_refuses_by_name_without_connecting(
    monkeypatch, capsys, value
) -> None:
    seen = _wire(monkeypatch=monkeypatch)
    monkeypatch.setenv(_VARIABLE, value)

    assert _boundary().current(query=_query()) is False
    assert seen["tcp"] == []
    assert seen["tls"] == []
    assert seen["connections"] == []
    err = capsys.readouterr().err
    assert _VARIABLE in err
    assert "controlled-query-token" not in err


@pytest.mark.parametrize(
    ("error", "stage"),
    [
        (ConnectionRefusedError("refused"), "dial_error"),
        (TimeoutError("timed out"), "dial_error"),
        (ssl.SSLCertVerificationError("hostname mismatch"), "tls_error"),
        (http.client.HTTPException("bad protocol"), "connect_error"),
    ],
)
def test_a_failed_override_read_names_the_error_class_and_the_address_it_tried(
    monkeypatch, capsys, error, stage
) -> None:
    seen = _wire(monkeypatch=monkeypatch, **{stage: error})
    monkeypatch.setenv(_VARIABLE, _ADDRESS)

    assert _boundary().current(query=_query()) is False
    assert seen["tcp"] == [{"address": (_ADDRESS, 8765), "timeout": _CEILING}]
    err = capsys.readouterr().err
    assert type(error).__name__ in err
    assert _ADDRESS + ":8765" in err
    assert _HOST in err
    assert "/current" in err
    assert "controlled-query-token" not in err


def test_a_failed_hostname_read_names_the_error_class_and_the_host_port(
    monkeypatch, capsys
) -> None:
    seen = _wire(monkeypatch=monkeypatch, connect_error=OSError("offline"))
    monkeypatch.delenv(_VARIABLE, raising=False)

    assert _boundary().admitted(query=_query()) is False
    assert seen["tcp"] == []
    err = capsys.readouterr().err
    assert "OSError" in err
    assert _HOST + ":8765" in err
    assert "/admitted" in err
    assert "controlled-query-token" not in err


def test_a_refused_precondition_still_says_nothing(monkeypatch, capsys) -> None:
    seen = _wire(monkeypatch=monkeypatch)
    monkeypatch.setenv(_VARIABLE, _ADDRESS)

    assert _boundary(url="https://controller.example:bad/api").current(query=_query()) is False
    assert seen["tcp"] == []
    assert seen["connections"] == []
    assert capsys.readouterr().err == ""
