"""The CI client can connect to the observer's tailnet address while verifying its hostname.

livespec-dev-tooling-ws2idp. Measured 2026-11-06 on the expedited-incident-response-flag
drill: a runner pod resolves `vps.perch-rudd.ts.net` through public DNS to Tailscale's
Funnel ingress (208.111.34.11), where the observer's tailnet port 8765 is not served, so
each `/current` and `/admitted` read hung to the client ceiling and the released plan
refused with `fresh current authority and independent admission required` (runs
42270391525 attempts 1 and 2, 123 s each). From the same pod,
`curl --resolve vps.perch-rudd.ts.net:8765:100.89.189.118` with certificate validation
answered 403 in 0.13 s. When the environment carries
`LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR`, a validated IPv4 or IPv6 literal, the client
opens its TCP connection to that address and the URL's port, wraps it with TLS using the
URL's hostname for SNI and certificate verification, and sends the URL's hostname as the
Host header. An invalid literal refuses without connecting; an unset variable keeps the
existing behaviour.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from livespec_dev_tooling import incident_ci_authority as module

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ws2idp
_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR"
_URL = "https://controller.example:8765/api"
_HOST = "controller.example"


def _query() -> dict[str, object]:
    return {
        "repository": "owner/repo",
        "arm_id": "d" * 64,
        "pr_number": 7,
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "receipt_digest": "e" * 64,
    }


def _boundary() -> module.CiAuthorityBoundary:
    return module.CiAuthorityBoundary(
        observer_url=_URL,
        observer_token="controlled-query-token",  # noqa: S106 — public fixture token.
    )


def _wire(*, monkeypatch) -> dict[str, list[object]]:
    """Capture every socket, TLS and HTTP step the client takes."""
    seen: dict[str, list[object]] = {
        "connections": [],
        "tcp": [],
        "tls": [],
        "requests": [],
        "socks": [],
    }

    class _Connection:
        def __init__(self, host, port=None, timeout=None, **kwargs):
            seen["connections"].append({"host": host, "port": port, "timeout": timeout, **kwargs})
            self.host = host
            self.sock = None

        def request(self, method, path, body=None, headers=None):  # noqa: ARG002 — the client passes body by keyword.
            seen["requests"].append(
                {"method": method, "path": path, "headers": dict(headers or {})}
            )
            seen["socks"].append(self.sock)

        def getresponse(self):
            route = seen["requests"][-1]["path"].rsplit("/", 1)[-1]
            raw = json.dumps({"schema": 1, "status": route, "query": _query()}).encode()
            return SimpleNamespace(status=202, read=lambda _: raw)

        def close(self):
            return None

    def create_connection(address, timeout=None, **_kwargs):
        seen["tcp"].append({"address": address, "timeout": timeout})
        return SimpleNamespace(kind="tcp", address=address)

    class _Context:
        def wrap_socket(self, sock, server_hostname=None, **_kwargs):
            seen["tls"].append({"sock": sock, "server_hostname": server_hostname})
            return SimpleNamespace(kind="tls", inner=sock, server_hostname=server_hostname)

    monkeypatch.setattr(module.http.client, "HTTPSConnection", _Connection)
    monkeypatch.setattr(
        module, "socket", SimpleNamespace(create_connection=create_connection), raising=False
    )
    monkeypatch.setattr(
        module, "ssl", SimpleNamespace(create_default_context=lambda: _Context()), raising=False
    )
    return seen


def test_an_override_address_is_dialed_while_the_url_host_is_verified_and_sent(
    monkeypatch,
) -> None:
    seen = _wire(monkeypatch=monkeypatch)
    monkeypatch.setenv(_VARIABLE, "100.89.189.118")

    assert _boundary().current(query=_query()) is True
    assert seen["tcp"] == [{"address": ("100.89.189.118", 8765), "timeout": 60}]
    assert [t["server_hostname"] for t in seen["tls"]] == [_HOST]
    assert seen["tls"][0]["sock"] is not None and seen["tls"][0]["sock"].kind == "tcp"
    assert [c["host"] for c in seen["connections"]] == [_HOST]
    assert seen["socks"] == [seen["tls"][0]["sock"]] or (
        seen["socks"] and getattr(seen["socks"][0], "kind", None) == "tls"
    )
    assert seen["requests"][0]["headers"].get("Host", _HOST) == _HOST


def test_an_ipv6_override_literal_is_dialed_the_same_way(monkeypatch) -> None:
    seen = _wire(monkeypatch=monkeypatch)
    monkeypatch.setenv(_VARIABLE, "fd7a:115c:a1e0::5f01:bd8d")

    assert _boundary().admitted(query=_query()) is True
    assert seen["tcp"] == [{"address": ("fd7a:115c:a1e0::5f01:bd8d", 8765), "timeout": 60}]
    assert [t["server_hostname"] for t in seen["tls"]] == [_HOST]


def test_without_the_variable_the_client_connects_by_hostname_as_before(monkeypatch) -> None:
    seen = _wire(monkeypatch=monkeypatch)
    monkeypatch.delenv(_VARIABLE, raising=False)

    assert _boundary().current(query=_query()) is True
    assert seen["tcp"] == []
    assert seen["tls"] == []
    assert [c["host"] for c in seen["connections"]] == [_HOST]
    assert seen["socks"] == [None]


def test_an_invalid_override_literal_refuses_without_connecting(monkeypatch) -> None:
    for value in (
        "vps.perch-rudd.ts.net",
        "100.89.189",
        " 100.89.189.118",
        "100.89.189.118:8765",
    ):
        seen = _wire(monkeypatch=monkeypatch)
        monkeypatch.setenv(_VARIABLE, value)

        assert _boundary().current(query=_query()) is False, value
        assert seen["tcp"] == [], value
        assert seen["connections"] == [], value
