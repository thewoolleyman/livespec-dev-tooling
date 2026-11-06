"""The observer's reader ceiling and the CI client's read ceiling outwait a real pass.

livespec-dev-tooling-ws2idp. The expedited-incident-response-flag drill measured
a generation-2 `read-current` pass on the dev host at 7.4 s (load 12), 9.2 s
(load 16) and a kill at 10.16 s (load 20) against the observer's 10 s reader
limit, so `POST /arm` refused `canonical pre-merge authority unavailable` with a
current, verified chain. The CI job makes about five observer reads per run,
each through a client whose own socket timeout was the same 10 s. Both
ceilings are named constants, the client's is longer than the reader's plus
the observer's overhead, and a reader slower than its ceiling still refuses.
"""

from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

from livespec_dev_tooling import incident_ci_authority, incident_observer_authority
from livespec_dev_tooling._incident_observer_types import ObserverArm

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ws2idp
_READER_CEILING = 45
_CLIENT_CEILING = 60


def _attempt() -> dict[str, object]:
    return {
        "repository": "owner/repo",
        "item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-2",
        "generation": 2,
        "owner": "owner",
        "base": "e" * 40,
        "head": "c" * 40,
        "pr_number": 55,
        "landed_commits": [],
        "landed_trees": [],
        "original_paths": ["module.py"],
        "deferred_work": [],
        "repayment_required": True,
    }


def _arm() -> ObserverArm:
    return ObserverArm(
        repository="owner/repo",
        incident_item_id="incident-1",
        attempt_id="repair-1",
        phase="repair",
        operation_id="operation-2",
        generation=2,
        owner="owner",
        pr_number=55,
        base_sha="e" * 40,
        head_sha="c" * 40,
        required_jobs=("ci-green",),
        controller_release="v1.2.3",
        controller_revision="b" * 40,
        authority_receipt=json.dumps(_attempt(), sort_keys=True, separators=(",", ":")).encode(),
    )


def _reader(*, tmp_path) -> incident_observer_authority.CurrentAuthorityReader:
    return incident_observer_authority.CurrentAuthorityReader(
        command=("installed-reader",),
        repo=tmp_path,
        release="v1.2.3",
        installed_reader_approved=lambda _release, _command: True,
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


def test_the_two_ceilings_are_named_and_the_client_outwaits_the_reader() -> None:
    reader_ceiling = getattr(incident_observer_authority, "_READER_TIMEOUT_SECONDS", None)
    client_ceiling = getattr(incident_ci_authority, "_OBSERVER_READ_TIMEOUT_SECONDS", None)

    assert reader_ceiling == _READER_CEILING
    assert client_ceiling == _CLIENT_CEILING
    assert isinstance(reader_ceiling, int) and isinstance(client_ceiling, int)
    assert client_ceiling > reader_ceiling


def test_the_reader_is_run_under_its_ceiling_and_a_slower_reader_still_refuses(
    tmp_path, monkeypatch
) -> None:
    reply = {
        "schema": 1,
        "status": "verified",
        "authorizes_current_effects": True,
        "result": {"is_current": True, "attempt": _attempt()},
    }
    outcomes: list[object] = [subprocess.CompletedProcess([], 0, json.dumps(reply), "")]
    seen: list[dict[str, object]] = []

    def run(_argv, **kwargs):
        seen.append(dict(kwargs))
        outcome = outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(subprocess, "run", run)
    reader = _reader(tmp_path=tmp_path)

    assert reader(_arm()) is True
    assert seen[-1]["timeout"] == _READER_CEILING

    outcomes[0] = subprocess.TimeoutExpired("installed-reader", _READER_CEILING)
    assert reader(_arm()) is False
    assert seen[-1]["timeout"] == _READER_CEILING


def test_the_ci_client_opens_its_connection_under_its_ceiling(monkeypatch) -> None:
    seen: list[dict[str, object]] = []
    raw = json.dumps({"schema": 1, "status": "current", "query": _query()}).encode()

    def connect(*_args, **kwargs):
        seen.append(dict(kwargs))
        response = SimpleNamespace(status=202, read=lambda _: raw)
        return SimpleNamespace(
            request=lambda *_a, **_k: None, getresponse=lambda: response, close=lambda: None
        )

    monkeypatch.setattr(incident_ci_authority.http.client, "HTTPSConnection", connect)
    boundary = incident_ci_authority.CiAuthorityBoundary(
        observer_url="https://controller.example/api",
        observer_token="controlled-query-token",  # noqa: S106 — public fixture token.
    )

    assert boundary.current(query=_query()) is True
    assert seen[-1]["timeout"] == _CLIENT_CEILING
