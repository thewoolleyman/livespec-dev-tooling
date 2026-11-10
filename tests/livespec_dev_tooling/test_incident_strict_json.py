"""Every incident JSON decoder refuses ambiguity through one strict decoder."""

from __future__ import annotations

import ast
import hashlib
import hmac
import http.client
import importlib
import io
import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
from returns.pipeline import is_successful

from livespec_dev_tooling import incident_ci_attachment as attachment_module
from livespec_dev_tooling import incident_ci_identity as identity_module
from livespec_dev_tooling import incident_ci_job_collection as collection_module
from livespec_dev_tooling import incident_hook_scope as scope_module
from livespec_dev_tooling._incident_observer_store import load_record
from livespec_dev_tooling.incident_authority_client import check_authority_reply
from livespec_dev_tooling.incident_observer_events import verify_leaf_completion
from livespec_dev_tooling.incident_release_entry import ScreenRequest, screen
from tests.livespec_dev_tooling import test_incident_ci_attachment_edges as edge_tests
from tests.livespec_dev_tooling import test_incident_hook_scope as scope_tests

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-utw7u6

trusted = edge_tests.trusted
correlated = edge_tests.correlated
authenticated = edge_tests.authenticated
attached = edge_tests.attached

_PACKAGE = Path(__file__).resolve().parents[2] / "livespec_dev_tooling"
_MODULE = "livespec_dev_tooling.incident_strict_json"
# Decoders of JSON this process wrote itself, or that a tool it ran just wrote for it
# (the coverage report); no foreign text reaches them.
_SELF_PRODUCED = {
    "_incident_focused_measurement.py",
    "_incident_release_types.py",
    "incident_run_collector.py",
}
_AMBIGUOUS = [
    '{"a":1,"a":2}',
    '{"outer":{"a":1,"a":2}}',
    '{"n":NaN}',
    '{"n":Infinity}',
    '{"n":-Infinity}',
    '{"n":1e999}',
    "{",
    "",
]


def _strict() -> Any:
    assert (_PACKAGE / "incident_strict_json.py").is_file()
    return importlib.import_module(_MODULE)


@pytest.mark.parametrize("text", _AMBIGUOUS)
def test_one_refusal_shape_for_every_ambiguous_or_malformed_text(text: str) -> None:
    module = _strict()
    for subject in (text, text.encode()):
        with pytest.raises(module.IncidentJsonRefusalError, match="incident JSON refused"):
            module.strict_json(text=subject, limit=None)


def test_bounds_encoding_and_nesting_refuse_through_the_same_shape() -> None:
    module = _strict()
    with pytest.raises(module.IncidentJsonRefusalError, match="bound"):
        module.strict_json(text='{"a":1}', limit=3)
    with pytest.raises(module.IncidentJsonRefusalError, match="UTF-8"):
        module.strict_json(text=b"\xff", limit=None)
    with pytest.raises(module.IncidentJsonRefusalError, match="nest"):
        module.strict_json(text="[" * 100000, limit=None)
    with pytest.raises(module.IncidentJsonRefusalError, match="malformed"):
        module.strict_json(text="1" * 5000, limit=None)


def test_unambiguous_text_decodes_for_str_and_bytes() -> None:
    module = _strict()
    expected = {"a": [1, 2.5, None, True], "b": {"c": "d"}}
    assert module.strict_json(text=json.dumps(expected), limit=1024) == expected
    assert module.strict_json(text=json.dumps(expected).encode(), limit=None) == expected


def test_the_named_decoders_share_the_strict_decoder() -> None:
    from livespec_dev_tooling._incident_ci_identity_json import identity_json
    from livespec_dev_tooling._incident_recovery_journal_values import JournalValues
    from livespec_dev_tooling.incident_ci_payload import strict_json as payload_json

    module = _strict()
    assert payload_json is module.strict_json
    for text in ('{"n":NaN}', '{"n":Infinity}', '{"a":1,"a":1}', '{"n":1e999}'):
        with pytest.raises(module.IncidentJsonRefusalError):
            payload_json(text=text)
        with pytest.raises(module.IncidentJsonRefusalError):
            identity_json(raw=text.encode())
        with pytest.raises(module.IncidentJsonRefusalError):
            JournalValues.decode(raw=text.encode(), limit=1024)


def _verified_reply(*, extra: str) -> str:
    response = {
        "schema": 1,
        "status": "verified",
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
        "result": {"attempt": {}},
    }
    return json.dumps(response)[:-1] + extra + "}"


def test_authority_reply_with_a_nonfinite_number_or_duplicate_key_is_refused() -> None:
    clean = check_authority_reply(
        action="read-history", returncode=0, stdout=_verified_reply(extra=""), stderr=""
    )
    assert is_successful(clean)
    for extra in (', "x": NaN', ', "x": Infinity', ', "x": 1e999', ', "schema": 1'):
        result = check_authority_reply(
            action="read-history", returncode=0, stdout=_verified_reply(extra=extra), stderr=""
        )
        assert not is_successful(result)


def _loads_calls(*, path: Path) -> list[str]:
    return [
        f"{path.name}:{node.lineno}"
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "json"
        and node.func.attr in {"loads", "load"}
    ]


def test_no_incident_module_decodes_foreign_json_outside_the_strict_decoder() -> None:
    offenders = [
        call
        for path in sorted(
            [*_PACKAGE.glob("*incident*.py"), *_PACKAGE.glob("checks/*incident*.py")]
        )
        if path.name != "incident_strict_json.py" and path.name not in _SELF_PRODUCED
        for call in _loads_calls(path=path)
    ]
    assert offenders == []


def _corrupt_read(**_: Any) -> Any:
    raise _strict().IncidentJsonRefusalError("incident JSON refused: duplicate key")


def test_a_refused_state_read_fails_closed_on_attach(attached, monkeypatch) -> None:
    handler = attachment_module.CiJobAttachment(installation=attached.application.installation)
    monkeypatch.setattr(attachment_module, "load_record", _corrupt_read)
    result = handler.execute(authorization="Bearer " + attached.token, payload=vars(attached.query))
    assert result["status"] == "refused"


def test_a_refused_state_read_fails_closed_on_collect_and_inspect(attached, monkeypatch) -> None:
    handler = collection_module.CiJobCollection(installation=attached.application.installation)
    monkeypatch.setattr(collection_module, "load_record", _corrupt_read)
    collect = {
        "repository": "owner/repo",
        "attachment_id": attached.receipt["attachment_id"],
        "collection_id": "c1",
    }
    inspect = {"repository": "owner/repo", "attachment_id": attached.receipt["attachment_id"]}
    assert handler.execute(path="/ci/jobs/collect", payload=collect)["status"] == "refused"
    assert handler.execute(path="/ci/jobs/inspect", payload=inspect)["status"] == "refused"


def test_a_refused_state_read_fails_closed_on_identity(authenticated, monkeypatch) -> None:
    application, query, token, *_ = authenticated
    monkeypatch.setattr(identity_module, "observer_arm_admitted", _corrupt_read)
    result = identity_module.CiIdentityVerifier(installation=application.installation).execute(
        authorization="Bearer " + token, payload=vars(query)
    )
    assert result == {
        "schema": 1,
        "status": "refused",
        "reason": "CI identity state or observations unavailable",
    }


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ('{"a":1,"a":2}', "duplicate-key"),
        ('{"n":NaN}', "non-finite"),
        ('{"n":-Infinity}', "non-finite"),
        ('{"n":1e999}', "non-finite"),
        ("[" * 100000, "nesting"),
        ("{", "malformed"),
    ],
)
def test_every_refusal_names_its_kind(text: str, kind: str) -> None:
    module = _strict()
    with pytest.raises(module.IncidentJsonRefusalError) as refused:
        module.strict_json(text=text, limit=None)
    assert refused.value.kind == kind


@pytest.mark.parametrize(
    ("stdout", "detail"),
    [
        (_verified_reply(extra=', "x": NaN'), "reply carries a non-finite number"),
        ("[" * 100000, "reply nests JSON too deeply"),
        (_verified_reply(extra=', "schema": 1'), "reply repeats a JSON key"),
    ],
)
def test_authority_refusal_detail_follows_the_refusal_kind(stdout: str, detail: str) -> None:
    result = check_authority_reply(action="read-history", returncode=0, stdout=stdout, stderr="")
    assert result.failure().detail == detail


_SOURCE = "a" * 40
_SCREEN_QUERY = {"repository": "owner/repo", "source_sha": _SOURCE, "tag": "v1.2.3"}
_SCREEN_ENVIRON = {
    "LIVESPEC_INCIDENT_OBSERVER_URL": "https://observer.example.invalid:8765",
    "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN": "query-token",
}


@pytest.mark.parametrize(
    "raw",
    [
        json.dumps({"schema": 1, "status": "clear", "query": _SCREEN_QUERY})[:-1]
        + ', "status": "clear"}',
        '{"status": "refused", "reason": "incident-release-recovery-retained", "detail": NaN}',
    ],
)
def test_release_entry_refuses_an_ambiguous_reply_as_malformed(raw: str) -> None:
    response = Mock(status=http.client.ACCEPTED)
    response.read.return_value = raw.encode()
    connection = Mock()
    connection.getresponse.return_value = response
    request = ScreenRequest(
        observed_repository="owner/repo", repository="owner/repo", source_sha=_SOURCE, tag="v1.2.3"
    )
    code, line = screen(
        request=request, environ=_SCREEN_ENVIRON, connect=Mock(return_value=connection)
    )
    assert (code, line) == (
        1,
        f"incident-release-screen-malformed-reply: HTTP {http.client.ACCEPTED} from the observer",
    )


@pytest.mark.parametrize(
    "body",
    [
        b'{"repository":"owner/repo","repository":"owner/repo"}',
        b'{"repository":"owner/repo","n":NaN}',
    ],
)
def test_control_route_refuses_an_ambiguous_body(authenticated, body: bytes) -> None:
    application, *_ = authenticated
    replies: list[str] = []
    environ = {
        "PATH_INFO": "/arm",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_AUTHORIZATION": "Bearer " + application.installation.control_secret.decode(),
        "wsgi.input": io.BytesIO(body),
    }
    raw = b"".join(application(environ, lambda status, _headers: replies.append(status)))
    assert (replies, json.loads(raw)) == (
        ["403 Forbidden"],
        {"status": "refused", "reason": "invalid control request or unavailable protected state"},
    )


# A duplicate key, NaN and an out-of-range exponent appended to an otherwise valid document.
_AMBIGUOUS_TAILS = [', "x": 1, "x": 2', ', "x": NaN', ', "x": 1e999']


def _with_tail(*, document: dict[str, Any], tail: str) -> bytes:
    return (json.dumps(document)[:-1] + tail + "}").encode()


@pytest.mark.parametrize("tail", _AMBIGUOUS_TAILS)
def test_controller_state_read_refuses_an_ambiguous_record(tmp_path: Path, tail: str) -> None:
    path = tmp_path / "record.json"
    path.write_bytes(_with_tail(document={"schema": 1}, tail=""))
    clean = load_record(path=path)
    path.write_bytes(_with_tail(document={"schema": 1}, tail=tail))
    with pytest.raises(_strict().IncidentJsonRefusalError):
        load_record(path=path)
    assert clean == {"schema": 1}


@pytest.mark.parametrize("tail", _AMBIGUOUS_TAILS)
def test_job_callback_refuses_an_ambiguous_signed_body(tail: str) -> None:
    secret = b"strict-json-fixture-secret"
    job = {
        "name": "coverage (3.12)",
        "head_sha": "a" * 40,
        "head_branch": "master",
        "conclusion": "failure",
        "run_id": 91,
        "id": 92,
        "status": "completed",
    }
    payload = {
        "action": "completed",
        "repository": {"full_name": "owner/repo"},
        "workflow_job": job,
    }

    def verify(*, body: bytes) -> object:
        return verify_leaf_completion(
            body=body,
            signature="sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest(),
            event="workflow_job",
            delivery_id="delivery-one",
            secret=secret,
        )

    clean = verify(body=_with_tail(document=payload, tail=""))
    ambiguous = verify(body=_with_tail(document=payload, tail=tail))
    assert (clean is not None, ambiguous) == (True, None)


def _scope_git(**kwargs: Any) -> str:
    replies = {"diff": "app.py", "ls-tree": "app.py", "rev-parse": "a" * 40}
    return replies.get(
        kwargs["args"][0], "# EXPEDITED_INCIDENT_RESPONSE flag: incident\nvalue = 2\n"
    )


def _validate_scope_against(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, reply: bytes
) -> Any:
    monkeypatch.setattr(scope_module, "git_text", _scope_git)
    monkeypatch.setattr(
        scope_module,
        "gh_read",
        lambda **_kwargs: subprocess.CompletedProcess([], 0, reply.decode(), ""),
    )
    return scope_module.validate_scope(
        repo=tmp_path,
        context=scope_tests.context(),
        reading={"attempt": scope_tests.attempt()},
        query={"repository": "owner/repo"},
        tree="d" * 40,
        call=scope_tests.push(f"refs/heads/repair {'b' * 40} refs/heads/repair {'c' * 40}\n"),
    )


@pytest.mark.parametrize("tail", [', "state": "open"', ', "x": NaN', ', "x": 1e999'])
def test_hook_scope_refuses_an_ambiguous_pull_request_read(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, tail: str
) -> None:
    clean = _validate_scope_against(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        reply=_with_tail(document=scope_tests.pr(), tail=""),
    )
    with pytest.raises(_strict().IncidentJsonRefusalError):
        _validate_scope_against(
            monkeypatch=monkeypatch,
            tmp_path=tmp_path,
            reply=_with_tail(document=scope_tests.pr(), tail=tail),
        )
    assert clean["marker"] == "app.py"
