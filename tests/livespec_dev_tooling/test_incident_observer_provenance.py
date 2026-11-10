"""The hosted range gate's provenance answer comes only from the installed reader."""

from __future__ import annotations

import ast
import io
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_observer_provenance as module
from livespec_dev_tooling._incident_provenance_types import IncidentCommitQuery
from livespec_dev_tooling.incident_observer_service import ControllerService

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
_HEAD = "b" * 40
_LANDED = "e" * 40
_LANDED_TREE = "f" * 40


def _query(**changes: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "repository": "owner/repo",
        "item_id": "incident-1",
        "attempt_id": "attempt-1",
        "phase": "repair",
        "operation_id": "operation-2",
        "generation": 2,
        "owner": "operator",
        "base": "a" * 40,
        "head": _HEAD,
        "pr_number": 7,
        "commit_sha": _HEAD,
        "tree_sha": "c" * 40,
    }
    return fields | changes


def _history(*, query: dict[str, object], landed: bool = False) -> str:
    attempt = {key: query[key] for key in query if key not in {"commit_sha", "tree_sha"}}
    attempt |= {
        "landed_commits": [_LANDED] if landed else [],
        "landed_trees": [_LANDED_TREE] if landed else [],
        "original_paths": ["livespec_dev_tooling/repair.py"],
        "deferred_work": [],
        "repayment_required": True,
    }
    return json.dumps(
        {
            "schema": 1,
            "status": "verified",
            "authorizes_current_effects": False,
            "normal_factory_proof": False,
            "result": {
                "attempt": attempt,
                "committed_token_id": "token-1",
                "current_token_id": "token-2",
            },
        }
    )


@pytest.fixture
def settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        repository="owner/repo",
        repo=tmp_path / "reference",
        reader=("/installed/python", "/installed/incident_authority.py"),
        query_secret=b"query" * 8,
        control_secret=b"control" * 8,
        webhook_secret=b"webhook" * 8,
    )


def _reader(
    *, monkeypatch: pytest.MonkeyPatch, stdout: str = "", returncode: int = 0, error: bool = False
) -> Mock:
    run = (
        Mock(side_effect=subprocess.TimeoutExpired(cmd="reader", timeout=45))
        if error
        else Mock(return_value=SimpleNamespace(stdout=stdout, stderr="", returncode=returncode))
    )
    monkeypatch.setattr(subprocess, "run", run)
    return run


def _execute(*, settings: SimpleNamespace, payload: dict[str, object]) -> dict[str, object]:
    return module.ObserverProvenance(installation=settings).execute(
        path="/provenance", payload=payload
    )


def test_a_recorded_head_is_answered_from_the_installed_history_reader(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = _query()
    run = _reader(monkeypatch=monkeypatch, stdout=_history(query=query))
    answer = _execute(settings=settings, payload=query)
    assert answer == {"schema": 1, "status": "provenance", "query": query}
    argv = run.call_args.args[0]
    assert argv[:3] == [*settings.reader, "read-history"]
    assert argv[argv.index("--generation") + 1] == "2"
    assert argv[argv.index("--item") + 1] == "incident-1"
    assert run.call_args.kwargs["cwd"] == settings.repo


def test_a_recorded_landed_pair_stays_admitted_with_no_arm_on_the_host(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = _query(commit_sha=_LANDED, tree_sha=_LANDED_TREE)
    _reader(monkeypatch=monkeypatch, stdout=_history(query=query, landed=True))
    assert _execute(settings=settings, payload=query)["status"] == "provenance"


def test_a_commit_the_chain_does_not_record_is_refused_by_name(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = _query(commit_sha="d" * 40)
    _reader(monkeypatch=monkeypatch, stdout=_history(query=query))
    assert _execute(settings=settings, payload=query) == {
        "schema": 1,
        "status": "refused",
        "reason": "incident-provenance-identity-mismatch",
    }


def test_a_reader_refusal_keeps_its_canonical_code(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    refusal = {
        "schema": 1,
        "status": "refused",
        "authorizes_current_effects": False,
        "normal_factory_proof": False,
        "result": {"code": "incident-authority-missing", "detail": "no chain"},
    }
    _reader(monkeypatch=monkeypatch, stdout=json.dumps(refusal), returncode=78)
    assert _execute(settings=settings, payload=_query())["reason"] == "incident-authority-missing"


def test_an_unavailable_reader_fails_closed(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reader(monkeypatch=monkeypatch, error=True)
    assert _execute(settings=settings, payload=_query())["reason"] == "incident-authority-timeout"


@pytest.mark.parametrize(
    "payload",
    [
        _query(phase="repayment-active"),
        _query(generation=0),
        _query(pr_number="7"),
        _query(owner=""),
        _query(head="short"),
        _query(extra="field"),
    ],
)
def test_an_inexact_query_never_reaches_the_reader(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, payload: dict[str, object]
) -> None:
    run = _reader(monkeypatch=monkeypatch)
    assert _execute(settings=settings, payload=payload)["status"] == "refused"
    assert run.call_count == 0


def test_the_service_routes_provenance_under_the_query_credential_only(
    settings: SimpleNamespace, monkeypatch: pytest.MonkeyPatch
) -> None:
    query = _query()
    _reader(monkeypatch=monkeypatch, stdout=_history(query=query))
    service = ControllerService(installation=settings, recover=Mock())
    assert asdict(IncidentCommitQuery(**query)) == query
    body = json.dumps(query).encode()

    def post(*, token: bytes) -> tuple[str, dict[str, object]]:
        started: list[str] = []
        environ = {
            "PATH_INFO": "/provenance",
            "REQUEST_METHOD": "POST",
            "HTTP_AUTHORIZATION": "Bearer " + token.decode(),
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/json",
            "wsgi.input": io.BytesIO(body),
        }
        reply = b"".join(
            service(environ, lambda status, headers: started.append(status))  # noqa: ARG005
        )
        return started[0], json.loads(reply)

    accepted = post(token=settings.query_secret)
    refused = post(token=settings.control_secret)
    assert accepted[0].startswith("202")
    assert accepted[1]["status"] == "provenance"
    assert refused[0].startswith("403")


def test_the_provenance_lookup_has_one_implementation_and_the_docs_name_it() -> None:
    root = Path(__file__).resolve().parents[2]
    assert not (root / "livespec_dev_tooling" / "incident_provenance.py").exists()
    doc = (root / "docs" / "incident-provenance.md").read_text()
    assert "incident_provenance.read_historical_incident_commit" not in doc
    assert "incident_observer_provenance" in doc


def _modules_matching(*, root: Path, wanted: str) -> set[str]:
    """Return the product modules under livespec_dev_tooling that use `wanted`.

    A module uses the decoder by importing the name, and uses the history read by
    passing the `read-history` action to `call_authority`.
    """
    found: set[str] = set()
    package = root / "livespec_dev_tooling"
    for path in package.rglob("*.py"):
        if "_vendor" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if wanted == "decoder":
                hit = isinstance(node, ast.ImportFrom) and any(
                    alias.name == "decode_historical_result" for alias in node.names
                )
            else:
                hit = (
                    isinstance(node, ast.Call)
                    and getattr(node.func, "id", getattr(node.func, "attr", "")) == "call_authority"
                    and any(
                        keyword.arg == "action"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value == "read-history"
                        for keyword in node.keywords
                    )
                )
            if hit:
                found.add(path.stem)
    return found


def test_only_the_observer_provenance_client_reads_history_for_commit_provenance() -> None:
    root = Path(__file__).resolve().parents[2]
    assert _modules_matching(root=root, wanted="decoder") == {"incident_observer_provenance"}
    assert _modules_matching(root=root, wanted="read-history") == {"incident_observer_provenance"}


def test_the_provenance_doc_describes_the_manifest_pinned_reader_not_a_credential_wrapper() -> None:
    root = Path(__file__).resolve().parents[2]
    doc = (root / "docs" / "incident-provenance.md").read_text()
    assert "credential wrapper" not in doc
    assert "with-livespec-env" not in doc
    assert "manifest-pinned" in doc
    assert "incident-observer-service.md" in doc


def test_the_module_docstring_names_the_shared_decoder_without_claiming_other_readers() -> None:
    docstring = module.__doc__ or ""
    assert "every other historical reader" not in docstring
    assert "_incident_provenance_protocol" in docstring
