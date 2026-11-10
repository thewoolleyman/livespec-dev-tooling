"""Every incident JSON decoder refuses ambiguity through one strict decoder."""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from returns.pipeline import is_successful

from livespec_dev_tooling import incident_ci_attachment as attachment_module
from livespec_dev_tooling import incident_ci_job_collection as collection_module
from livespec_dev_tooling.incident_authority_client import check_authority_reply
from tests.livespec_dev_tooling import test_incident_ci_attachment_edges as edge_tests

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-utw7u6

trusted = edge_tests.trusted
correlated = edge_tests.correlated
authenticated = edge_tests.authenticated
attached = edge_tests.attached

_PACKAGE = Path(__file__).resolve().parents[2] / "livespec_dev_tooling"
_MODULE = "livespec_dev_tooling.incident_strict_json"
# Decoders of bytes this process just produced itself; no foreign text reaches them.
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
        for path in sorted(_PACKAGE.glob("*incident*.py"))
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
