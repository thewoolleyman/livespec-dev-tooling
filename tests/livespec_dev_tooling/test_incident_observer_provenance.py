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


# The provenance guard. A second implementation of the commit-provenance history
# read must fail a test, whatever spelling it uses, so the guard keys on what the
# read cannot avoid saying rather than on one call shape:
#
# - "history": the `read-history` action as a string value anywhere outside a
#   docstring, after folding constants (concatenation, f-strings, `%`, `join`,
#   `format`, and names bound to such values in the same module). It catches a
#   `call_authority`/`invoke_authority`/`ports.authority` call under any import
#   form or alias, a `**{"action": ...}` splat, and a hand-built subprocess argv.
# - "decoder": any reference to the `_incident_provenance_protocol` module or to
#   `decode_historical_result` (import, from-import, alias, attribute access, or a
#   string such as an `importlib` target).
# - "authority": any reference to the authority-call helpers (`call_authority`,
#   `invoke_authority`, `registered_authority_command`, the
#   `incident_authority_client` module) or to the `incident_authority.py` script.
#
# Each signal's module set must EQUAL a reviewed allowlist, so a new reader has
# to edit this file to land. The scan covers every non-test `.py` git knows
# about (tracked or untracked-and-unignored) across the whole repository, which
# includes livespec_dev_tooling/ (and its checks/) and scripts/.

_PROVENANCE_READER = "livespec_dev_tooling/incident_observer_provenance.py"

# The history readers, each named with what it reads the attempt history FOR.
# Only the first answers commit provenance; the others read it for an
# attempt's own identity and do not decode a provenance reply.
_HISTORY_READERS: dict[str, str] = {
    _PROVENANCE_READER: "commit provenance for the hosted range gate (the one implementation)",
    "livespec_dev_tooling/_incident_original_run_canonical.py": (
        "authenticates an original run's identity against the attempt record"
    ),
    "livespec_dev_tooling/incident_focused_evidence_entry.py": (
        "confirms the attempt and head a focused-evidence record measured"
    ),
    "livespec_dev_tooling/incident_original_run_flows.py": (
        "reads the attempt's PR number for original-run collection"
    ),
}

# The decoder's own module defines it; the provenance reader is its one caller.
_DECODER_USERS = frozenset(
    {"livespec_dev_tooling/_incident_provenance_protocol.py", _PROVENANCE_READER}
)

_AUTHORITY_USERS = frozenset(
    {
        "livespec_dev_tooling/_incident_original_run_ports.py",
        "livespec_dev_tooling/incident_authority_client.py",
        "livespec_dev_tooling/incident_focused_evidence_entry.py",
        "livespec_dev_tooling/incident_gate_entry.py",
        "livespec_dev_tooling/incident_hook_entry.py",
        "livespec_dev_tooling/incident_hook_process.py",
        "livespec_dev_tooling/incident_observer_authority.py",
        "livespec_dev_tooling/incident_observer_provenance.py",
    }
)

_HISTORY_ACTION = "read-history"
_DECODER_WORDS = frozenset({"_incident_provenance_protocol", "decode_historical_result"})
_AUTHORITY_WORDS = frozenset(
    {
        "call_authority",
        "invoke_authority",
        "registered_authority_command",
        "incident_authority_client",
    }
)
_AUTHORITY_SCRIPT = "incident_authority.py"
_FOLD_LIMIT = 64


def _docstring_ids(*, tree: ast.Module) -> set[int]:
    owners = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    found: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, owners) or not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
            found.add(id(first.value))
    return found


def _product(left: set[str], right: set[str]) -> set[str]:
    return set(sorted(a + b for a in left for b in right)[:_FOLD_LIMIT])


def _single(folded: list[set[str]]) -> tuple[str, ...] | None:
    """Return the one value of each folded piece, or None when any is unknown or ambiguous."""
    if not all(len(piece) == 1 for piece in folded):
        return None
    return tuple(next(iter(piece)) for piece in folded)


def _fold_joined(node: ast.JoinedStr, names: dict[str, set[str]]) -> set[str]:
    values: set[str] = {""}
    for part in node.values:
        inner = part.value if isinstance(part, ast.FormattedValue) else part
        folded = _fold(inner, names)
        if not folded:
            return set()
        values = _product(values, folded)
    return values


def _fold_operator(node: ast.BinOp, names: dict[str, set[str]]) -> set[str]:
    left = _fold(node.left, names)
    if isinstance(node.op, ast.Add):
        return _product(left, _fold(node.right, names))
    if not isinstance(node.op, ast.Mod):
        return set()
    parts = node.right.elts if isinstance(node.right, ast.Tuple) else [node.right]
    args = _single([_fold(part, names) for part in parts])
    if args is None:
        return set()
    return {template % args for template in left if template.count("%s") == len(args)}


def _fold_method(node: ast.Call, names: dict[str, set[str]]) -> set[str]:
    if not isinstance(node.func, ast.Attribute) or node.keywords:
        return set()
    owner = _fold(node.func.value, names)
    if node.func.attr == "format":
        args = _single([_fold(arg, names) for arg in node.args])
        return set() if args is None else {template.format(*args) for template in owner}
    sequence = node.args[0] if len(node.args) == 1 else None
    if node.func.attr != "join" or not isinstance(sequence, ast.List | ast.Tuple):
        return set()
    pieces = _single([_fold(element, names) for element in sequence.elts])
    return set() if pieces is None else {separator.join(pieces) for separator in owner}


def _fold(node: ast.AST, names: dict[str, set[str]]) -> set[str]:
    """Return every string value `node` can be shown to produce from constants."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.Name):
        return set(names.get(node.id, set()))
    if isinstance(node, ast.JoinedStr):
        return _fold_joined(node, names)
    if isinstance(node, ast.BinOp):
        return _fold_operator(node, names)
    if isinstance(node, ast.Call):
        return _fold_method(node, names)
    return set()


def _bound_names(*, tree: ast.Module) -> dict[str, set[str]]:
    """Resolve names bound (anywhere in the module) to foldable string values."""
    bindings: list[tuple[str, ast.AST]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            bindings.extend(
                (target.id, node.value) for target in node.targets if isinstance(target, ast.Name)
            )
        single = isinstance(node, ast.AnnAssign | ast.NamedExpr)
        if single and isinstance(node.target, ast.Name) and node.value is not None:
            bindings.append((node.target.id, node.value))
    names: dict[str, set[str]] = {}
    for _ in range(4):
        for name, value in bindings:
            names.setdefault(name, set()).update(_fold(value, names))
    return names


def _identifiers(node: ast.AST) -> set[str]:
    """Return the identifiers `node` spells: names, attributes, definitions and imports."""
    words: set[str] = set()
    if isinstance(node, ast.alias):
        words.update(node.name.split("."))
    if isinstance(node, ast.ImportFrom) and node.module:
        words.update(node.module.split("."))
    for field in ("id", "attr", "name", "asname", "arg"):
        value = getattr(node, field, None)
        if isinstance(value, str):
            words.add(value)
    return words


def _signals(source: str) -> set[str]:
    """Name which of the history, decoder and authority signals `source` carries."""
    tree = ast.parse(source)
    docstrings = _docstring_ids(tree=tree)
    names = _bound_names(tree=tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        words = _identifiers(node)
        strings: set[str] = set() if id(node) in docstrings else _fold(node, names)
        tokens = {token for value in strings for token in value.split()}
        if _HISTORY_ACTION in strings or _HISTORY_ACTION in tokens:
            found.add("history")
        if words & _DECODER_WORDS or any(w in v for v in strings for w in _DECODER_WORDS):
            found.add("decoder")
        if (
            words & _AUTHORITY_WORDS
            or any(w in v for v in strings for w in _AUTHORITY_WORDS)
            or any(v.endswith(_AUTHORITY_SCRIPT) for v in strings | tokens)
        ):
            found.add("authority")
    return found


def _scanned_modules(*, root: Path) -> dict[str, str]:
    """Every non-test `.py` git knows about, tracked or untracked-and-unignored."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.py"],
        cwd=root,
        capture_output=True,
        check=True,
    ).stdout.decode()
    modules: dict[str, str] = {}
    for rel in filter(None, listed.split("\0")):
        path = root / rel
        parts = Path(rel).parts
        is_test = parts[0] == "tests" or path.name.startswith("test_") or path.name == "conftest.py"
        if is_test or "_vendor" in parts or not path.is_file():
            continue
        modules[rel] = path.read_text()
    return modules


def _modules_carrying(*, root: Path, signal: str) -> set[str]:
    return {
        rel for rel, source in _scanned_modules(root=root).items() if signal in _signals(source)
    }


def test_the_guard_scans_every_non_test_module_including_checks_and_scripts(
    tmp_path: Path,
) -> None:
    root = Path(__file__).resolve().parents[2]
    scanned = _scanned_modules(root=root)
    assert _PROVENANCE_READER in scanned
    assert any(rel.startswith("livespec_dev_tooling/checks/") for rel in scanned)
    assert not any(rel.startswith("tests/") for rel in scanned)
    assert not any("/_vendor/" in rel for rel in scanned)
    _ = subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    layout = {
        "scripts/reader.py": "history",
        "checks/reader.py": "history",
        "livespec_dev_tooling/checks/reader.py": "history",
        "livespec_dev_tooling/_vendor/lib/reader.py": "skipped",
        "tests/test_reader.py": "skipped",
        "scripts/test_reader.py": "skipped",
    }
    for rel in layout:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        _ = (tmp_path / rel).write_text('ACTION = "read-history"\n')
    wanted = {rel for rel, kind in layout.items() if kind == "history"}
    assert _modules_carrying(root=tmp_path, signal="history") == wanted


def test_only_allowlisted_modules_perform_the_history_read() -> None:
    root = Path(__file__).resolve().parents[2]
    assert _modules_carrying(root=root, signal="history") == set(_HISTORY_READERS)


def test_only_the_observer_provenance_client_decodes_a_provenance_reply() -> None:
    root = Path(__file__).resolve().parents[2]
    assert _modules_carrying(root=root, signal="decoder") == _DECODER_USERS


def test_only_allowlisted_modules_reach_the_authority_call_helpers() -> None:
    root = Path(__file__).resolve().parents[2]
    assert _modules_carrying(root=root, signal="authority") == _AUTHORITY_USERS


_SECOND_READERS: dict[str, tuple[str, str]] = {
    "plain-call": (
        'call_authority(command=r, action="read-history", flags={}, cwd=c)\n',
        "history",
    ),
    "module-attribute": (
        'client.call_authority(action="read-history", command=r, flags={}, cwd=c)\n',
        "history",
    ),
    "aliased-decoder-name": (
        "from livespec_dev_tooling._incident_provenance_protocol import "
        "decode_historical_result as d\n",
        "decoder",
    ),
    "subprocess-splat-argv": (
        'import subprocess\nsubprocess.run([*reader, "read-history", "--repo", "x"])\n',
        "history",
    ),
    "subprocess-literal-argv": (
        "import subprocess\n"
        'subprocess.run(["/opt/r/bin/incident_authority.py", "read-history"])\n',
        "history",
    ),
    "aliased-call-authority": (
        "from livespec_dev_tooling.incident_authority_client import call_authority as authority\n",
        "authority",
    ),
    "concatenated-action": ('authority(command=r, action="read-" + "history")\n', "history"),
    "named-constant": ('_ACTION = "read-history"\nauthority(action=_ACTION)\n', "history"),
    "folded-named-constant": (
        '_A = "read-"\n_B = _A + "hist"\nauthority(action=f"{_B}ory")\n',
        "history",
    ),
    "kwargs-splat": ('authority(**{"action": "read-history", "command": r})\n', "history"),
    "invoke-authority": ('invoke_authority(repo=r, query=q, action="read-history")\n', "history"),
    "aliased-decoder-module": (
        "from livespec_dev_tooling import _incident_provenance_protocol as p\n"
        "p.decode_historical_result(result=x, query=q)\n",
        "decoder",
    ),
    "imported-decoder-module": (
        "import livespec_dev_tooling._incident_provenance_protocol\n",
        "decoder",
    ),
    "relative-decoder-import": ("from . import _incident_provenance_protocol\n", "decoder"),
    "importlib-decoder": (
        "import importlib\n"
        'importlib.import_module("livespec_dev_tooling." + "_incident_provenance_protocol")\n',
        "decoder",
    ),
    "aliased-client-module": (
        "from livespec_dev_tooling import incident_authority_client as c\nc.call_authority\n",
        "authority",
    ),
    "getattr-helper": ('getattr(client, "invoke_" + "authority")\n', "authority"),
    "joined-action": ('authority(action="-".join(["read", "history"]))\n', "history"),
    "formatted-action": ('authority(action="read-{}".format("history"))\n', "history"),
    "percent-action": ('authority(action="read-%s" % "history")\n', "history"),
    "shell-string": (
        'os.system("python incident_authority.py read-history --repo x")\n',
        "history",
    ),
}


@pytest.mark.parametrize("shape", sorted(_SECOND_READERS))
def test_the_guard_flags_a_second_reader_in_every_known_shape(shape: str) -> None:
    source, signal = _SECOND_READERS[shape]
    assert signal in _signals(source)


@pytest.mark.parametrize(
    "source",
    [
        '"""Mentions read-history and _incident_provenance_protocol only in prose."""\n',
        'authority(action="read-current", flags={})\n',
        'LABEL = "read-history-ish"\n',
        "def history_reader() -> None:\n    pass\n",
    ],
)
def test_the_guard_does_not_flag_prose_or_other_actions(source: str) -> None:
    assert _signals(source) == set()


def test_the_provenance_doc_describes_the_manifest_pinned_reader_not_a_credential_wrapper() -> None:
    root = Path(__file__).resolve().parents[2]
    doc = (root / "docs" / "incident-provenance.md").read_text()
    assert "credential wrapper" not in doc
    assert "with-livespec-env" not in doc
    assert "manifest-pinned" in doc
    assert "incident-observer-service.md" in doc


def test_the_provenance_doc_keeps_the_action_out_of_the_manifest_reader_argv() -> None:
    root = Path(__file__).resolve().parents[2]
    doc = " ".join((root / "docs" / "incident-provenance.md").read_text().split())
    assert "incident_authority.py read-history" not in doc
    assert "`[<interpreter>, <installed incident_authority.py>]`" in doc
    assert "render_released_installation.py" in doc
    assert '`call_authority` runs `[*reader, "read-history"' in doc
    assert "Do not add `read-history`" in doc


def test_the_module_docstring_names_the_shared_decoder_without_claiming_other_readers() -> None:
    docstring = module.__doc__ or ""
    assert "every other historical reader" not in docstring
    assert "_incident_provenance_protocol" in docstring
