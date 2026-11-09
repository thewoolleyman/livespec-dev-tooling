"""A refused incident plan names the observer's non-202 status; mismatch refusals stay as they are.

livespec-dev-tooling-upb4k5. The drill on 2026-11-06 measured the incident-ci job
refusing with "fresh current authority and independent admission required" and nothing
else. The connect-failure half of the fix names the error class and the host:port the
client tried; this module holds the other two conditions. An observer that answers with
any status other than 202 is named by that status on the same refusal line, never with
the token or the reply body. A plan refused for a payload or identity mismatch reaches no
observer, so it keeps today's refusal result and the policy's mismatch code unchanged,
and writes no observer line.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from livespec_dev_tooling import incident_ci_authority as authority
from livespec_dev_tooling import incident_ci_process as process
from livespec_dev_tooling.incident_ci_payload import decode_authority
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiTarget, CiTrust, select_ci_plan
from livespec_dev_tooling.incident_execution import IncidentConfigurationRefusal
from tests.livespec_dev_tooling.test_incident_ci_payload import packet

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-upb4k5
_VARIABLE = "LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR"
_URL = "https://controller.example:8765/api"
_HOST = "controller.example"
_ADDRESS = "100.89.189.118"
_TOKEN = "controlled-query-token"
_REASON = "fresh current authority and independent admission required"
_TARGETS = (
    CiTarget(name="check-fast", classification="fast"),
    CiTarget(name="check-slow", classification="slow"),
)


def _query() -> dict[str, object]:
    return {
        "repository": "owner/repo",
        "arm_id": "d" * 64,
        "pr_number": 7,
        "base_sha": "a" * 40,
        "head_sha": "b" * 40,
        "receipt_digest": "e" * 64,
    }


def _event(*, head_sha: str = "b" * 40) -> CiEvent:
    return CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha=head_sha,
        pr_number=7,
        labels=("expedited-incident-response",),
    )


def _wire(*, monkeypatch, status: int = 202, error: Exception | None = None) -> list[object]:
    """Answer every observer read with one status, or raise one error, and record each dial."""
    dials: list[object] = []
    body = b'{"detail":"' + _TOKEN.encode() + b' echoed by a hostile proxy"}'

    class _Connection:
        def __init__(self, host, port=None, timeout=None, **_kwargs):
            dials.append((host, port, timeout))
            self.sock = None

        def request(self, *_args, **_kwargs):
            if error is not None:
                raise error

        def getresponse(self):
            return SimpleNamespace(status=status, read=lambda _: body)

        def close(self):
            return None

    def create_connection(address, timeout=None, **_kwargs):
        dials.append(("tcp", address, timeout))
        return SimpleNamespace(close=lambda: None)

    class _Context:
        def wrap_socket(self, sock, server_hostname=None, **_kwargs):
            return SimpleNamespace(inner=sock, server_hostname=server_hostname)

    monkeypatch.setattr(authority.http.client, "HTTPSConnection", _Connection)
    monkeypatch.setattr(
        authority, "socket", SimpleNamespace(create_connection=create_connection), raising=False
    )
    monkeypatch.setattr(
        authority, "ssl", SimpleNamespace(create_default_context=lambda: _Context()), raising=False
    )
    return dials


def _boundary() -> authority.CiAuthorityBoundary:
    return authority.CiAuthorityBoundary(observer_url=_URL, observer_token=_TOKEN)


@pytest.mark.parametrize("status", [301, 401, 403, 404, 500, 503])
@pytest.mark.parametrize("route", ["current", "admitted"])
def test_a_non_202_observer_answer_is_named_by_its_status(monkeypatch, capsys, status, route):
    _ = _wire(monkeypatch=monkeypatch, status=status)
    monkeypatch.delenv(_VARIABLE, raising=False)

    assert getattr(_boundary(), route)(query=_query()) is False
    err = capsys.readouterr().err
    assert err == (
        "incident-ci: observer read refused: HTTP "
        + str(status)
        + " while reading /"
        + route
        + " from "
        + _HOST
        + ":8765 as "
        + _HOST
        + "\n"
    )
    assert _TOKEN not in err


def test_a_non_202_answer_through_the_override_names_the_dialed_address(monkeypatch, capsys):
    dials = _wire(monkeypatch=monkeypatch, status=503)
    monkeypatch.setenv(_VARIABLE, _ADDRESS)

    assert _boundary().current(query=_query()) is False
    assert ("tcp", (_ADDRESS, 8765), 630) in dials
    err = capsys.readouterr().err
    assert "HTTP 503 while reading /current from " + _ADDRESS + ":8765 as " + _HOST in err
    assert _TOKEN not in err


def test_an_accepted_answer_writes_no_refusal_line(monkeypatch, capsys):
    _ = _wire(monkeypatch=monkeypatch, status=202)
    monkeypatch.delenv(_VARIABLE, raising=False)

    assert _boundary().current(query=_query()) is False
    assert capsys.readouterr().err == ""


def _incident_process(*, monkeypatch, tmp_path, event: CiEvent, payload: str) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "pull_request")
    monkeypatch.setenv("LIVESPEC_INCIDENT_OBSERVER_URL", _URL)
    monkeypatch.setenv("LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN", _TOKEN)
    monkeypatch.delenv(_VARIABLE, raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.setattr(process, "load_inventory", lambda: _TARGETS)
    monkeypatch.setattr(process, "observe_event", lambda **_: (event, payload))


@pytest.mark.parametrize(
    ("status", "error", "named"),
    [
        (503, None, "HTTP 503 while reading /current from " + _HOST + ":8765 as " + _HOST),
        (
            202,
            ConnectionRefusedError("refused"),
            "ConnectionRefusedError while reading /current from " + _HOST + ":8765 as " + _HOST,
        ),
    ],
)
def test_a_refused_incident_plan_names_the_observer_cause_beside_its_result(
    monkeypatch, tmp_path, capsys, status, error, named
):
    _incident_process(
        monkeypatch=monkeypatch, tmp_path=tmp_path, event=_event(), payload=json.dumps(packet())
    )
    _ = _wire(monkeypatch=monkeypatch, status=status, error=error)

    assert process.main(argv=["plan"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "refused", "reason": _REASON}
    assert captured.err == "incident-ci: observer read refused: " + named + "\n"
    assert _TOKEN not in captured.out + captured.err


@pytest.mark.parametrize(
    ("event", "payload"),
    [
        (_event(), "not an incident packet"),
        (_event(), json.dumps(packet() | {"observer_arm_id": "f" * 64})),
        (_event(head_sha="f" * 40), json.dumps(packet())),
    ],
    ids=["unparseable-payload", "payload-arm-mismatch", "identity-mismatch"],
)
def test_a_mismatch_refusal_keeps_its_result_and_reads_no_observer(
    monkeypatch, tmp_path, capsys, event, payload
):
    _incident_process(monkeypatch=monkeypatch, tmp_path=tmp_path, event=event, payload=payload)
    dials = _wire(monkeypatch=monkeypatch, status=503)

    assert process.main(argv=["plan"]) == 2
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"status": "refused", "reason": _REASON}
    assert captured.err == ""
    assert dials == []


def test_an_identity_mismatch_keeps_its_policy_code_before_any_observer_read():
    reads: list[str] = []
    decoded = decode_authority(payload=json.dumps(packet()))
    assert decoded is not None

    result = select_ci_plan(
        event=_event(head_sha="f" * 40),
        targets=_TARGETS,
        authority=decoded,
        trust=CiTrust(
            current=lambda _: reads.append("current") is not None,
            observer=lambda _a, _e: reads.append("admitted") is not None,
        ),
        environ={},
    )

    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-identity-mismatch"
    assert reads == []
