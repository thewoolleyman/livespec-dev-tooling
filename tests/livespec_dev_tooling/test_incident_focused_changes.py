"""`/arm` judges a focused-evidence record against the head's ACTUAL changed product files.

livespec-dev-tooling-6ou5m2: admission used to read the record's OWN `paths` and
`coverage`, so a hand-built or stale record with `paths: {}` was admitted however
much product code the head touched. The observer now computes the changed set
itself, in its own reference clone (the merge base of the target branch and the
head, then the head), and refuses a record that omits a changed product file or
leaves a changed executable product file without a coverage row.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-4aksht
from __future__ import annotations

import io
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from livespec_dev_tooling import incident_observer_control as control
from livespec_dev_tooling import incident_observer_service as service
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_focused_admission import (
    EVIDENCE_ROW,
    EvidenceSubject,
    evidence_receipt_id,
)

__all__: list[str] = []

_CHECKSUM = "sha256:" + "1" * 64
_REAL_RUN = subprocess.run
_GIT_ENV = (
    "GIT_DIR",
    "GIT_INDEX_FILE",
    "GIT_WORK_TREE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
)
_CONFIG = '[tool.livespec_dev_tooling]\nsource_trees = ["src"]\n'
# The head's changed product files: two executable modules and one docstring-only module.
_PRODUCT = ("src/doc_only.py", "src/gadget.py", "src/widget.py")
_EXECUTABLE = ("src/gadget.py", "src/widget.py")
# An executable product module the base has and the head deletes.
_RETIRED = "src/retired.py"


def _git(*, repo: Path, args: list[str]) -> str:
    done = _REAL_RUN(
        ["git", "-c", "user.name=Fixture", "-c", "user.email=f@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return done.stdout.strip()


@dataclass(frozen=True, kw_only=True)
class _Clone:
    repo: Path
    base: str
    head: str
    tree: str


def _commit(*, repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        _ = (repo / name).write_text(text, encoding="utf-8")
    _ = _git(repo=repo, args=["add", "-A"])
    _ = _git(repo=repo, args=["commit", "-qm", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _clone(
    *, root: Path, config: str = _CONFIG, target_ref: bool = True, retired: bool = False
) -> _Clone:
    repo = root / "repo"
    repo.mkdir()
    _ = _git(repo=repo, args=["init", "-q", "-b", "master"])
    base_files = {"pyproject.toml": config, "src/widget.py": "VALUE = 1\n", "README.md": "a\n"}
    if retired:
        base_files[_RETIRED] = "def retired() -> int:\n    return 0\n"
    base = _commit(repo=repo, files=base_files, message="base")
    if target_ref:
        _ = _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", base])
    if retired:
        (repo / _RETIRED).unlink()
    head = _commit(
        repo=repo,
        files={
            "src/widget.py": "VALUE = 2\n",
            "src/gadget.py": "def gadget() -> int:\n    return 1\n",
            "src/doc_only.py": '"""Only a docstring."""\n',
            "README.md": "b\n",
            "tests/test_gadget.py": "def test_gadget() -> None:\n    pass\n",
        },
        message="head",
    )
    _ = _git(repo=repo, args=["checkout", "-q", base])
    return _Clone(
        repo=repo, base=base, head=head, tree=_git(repo=repo, args=["rev-parse", head + "^{tree}"])
    )


def _attempt(*, clone: _Clone) -> dict[str, Any]:
    return {
        "repository": "owner/repo",
        "item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": "owner",
        "base": clone.base,
        "head": clone.head,
        "pr_number": 55,
        "landed_commits": [],
    }


def _record(*, clone: _Clone, paths: dict[str, str], covered: tuple[str, ...]) -> dict[str, Any]:
    return {
        "mode": "expedited-repair",
        "scope": "focused-tests-and-touched-files",
        "tree_hash": clone.tree,
        "identity": {
            "incident_item_id": "incident-1",
            "attempt_id": "repair-1",
            "repository": "owner/repo",
            "head_sha": clone.head,
            "operation_id": "operation-1",
        },
        "paths": paths,
        "selection": {"tests": [], "deferred_tests": {}},
        "manual": {"procedure": "p", "expected": "e", "observed": "e", "outcome": "passed"},
        "tests": {"returncode": 0, "timed_out": False},
        "coverage_command": {"returncode": 0, "timed_out": False},
        "coverage": {name: {"summary": {"percent_covered": 100}} for name in covered},
        "risks": [],
        "outcome": "passed",
    }


_HONEST = {
    "README.md": "non-executable",
    "src/doc_only.py": "non-executable",
    "src/gadget.py": "executable",
    "src/widget.py": "executable",
    "tests/test_gadget.py": "non-executable",
}


class _Authority:
    """The canonical reader's answers; every `git` call reaches the real reference clone."""

    def __init__(self, *, clone: _Clone) -> None:
        self.clone = clone
        self.receipts: dict[str, dict[str, Any]] = {}
        self.actions: list[str] = []

    def add(self, *, record: dict[str, Any]) -> None:
        subject = EvidenceSubject(
            repository="owner/repo",
            item="incident-1",
            attempt="repair-1",
            operation="operation-1",
            generation=1,
            head=self.clone.head,
            tree=self.clone.tree,
        )
        receipt_id = evidence_receipt_id(subject=subject, slot=0)
        self.receipts[receipt_id] = {
            "receipt_id": receipt_id,
            "hook": "pre-push",
            "tree": self.clone.tree,
            "mode": "expedited-repair",
            "evidence_kind": "expedited-local-partial",
            "exit_status": 0,
            "results": [{"name": EVIDENCE_ROW, "status": "passed", "output": json.dumps(record)}],
        }

    def __call__(self, argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        if argv[0] == "git":
            return cast("subprocess.CompletedProcess[Any]", _REAL_RUN(argv, **kwargs))
        action = argv[1]
        self.actions.append(action)
        result: dict[str, Any] = {"is_current": True, "attempt": _attempt(clone=self.clone)}
        if action == "read-local-gates":
            receipt_id = argv[argv.index("--receipt-id") + 1]
            receipt = self.receipts.get(receipt_id)
            result = {
                "status": "absent" if receipt is None else "recorded",
                "receipt_id": receipt_id,
                "committed_token_id": "committed",
                "current_token_id": "current",
                "checksum": None if receipt is None else _CHECKSUM,
                "receipt": receipt,
            }
        reply = {
            "schema": 1,
            "status": "verified",
            "authorizes_current_effects": action == "read-current",
            "normal_factory_proof": False,
            "result": result,
        }
        return subprocess.CompletedProcess(argv, 0, json.dumps(reply), "")


def _observer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, clone: _Clone
) -> tuple[service.ControllerService, _Authority]:
    for name in _GIT_ENV:
        monkeypatch.delenv(name, raising=False)
    settings = ControllerInstallation(
        repository="owner/repo",
        repo=clone.repo,
        state=tmp_path / "state",
        reader=("/installed/reader",),
        reader_release="v0.304.0",
        principal=("/installed/principal",),
        release="v1.169.0",
        revision="b" * 40,
        jobs=("coverage",),
        webhook_secret=b"webhook" * 8,
        control_secret=b"control" * 8,
        query_secret=b"query" * 8,
        port=8765,
        config=tmp_path / "controller.json",
    )
    authority = _Authority(clone=clone)
    monkeypatch.setattr(subprocess, "run", authority)

    def installed(**_: object) -> Callable[[str], object]:
        commits = {
            f"repos/owner/repo/git/commits/{clone.head}": {
                "sha": clone.head,
                "tree": {"sha": clone.tree},
            }
        }
        return commits.get

    monkeypatch.setattr(control.ForgeReads, "installed", installed)
    application = service.ControllerService(installation=settings, recover=lambda _: None)
    return application, authority


def _arm(
    *, application: service.ControllerService, clone: _Clone, base_sha: str | None = None
) -> tuple[str, dict[str, Any]]:
    payload = {
        "repository": "owner/repo",
        "incident_item_id": "incident-1",
        "attempt_id": "repair-1",
        "phase": "repair",
        "operation_id": "operation-1",
        "generation": 1,
        "owner": "owner",
        "base_sha": base_sha or clone.base,
        "head_sha": clone.head,
        "pr_number": 55,
        "authority_receipt": json.dumps(
            _attempt(clone=clone), sort_keys=True, separators=(",", ":")
        )
        .encode()
        .hex(),
    }
    body = json.dumps(payload).encode()
    environ = {
        "PATH_INFO": "/arm",
        "REQUEST_METHOD": "POST",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
        "HTTP_AUTHORIZATION": "Bearer " + application.installation.control_secret.decode(),
    }
    statuses: list[str] = []
    data = b"".join(application(environ, lambda status, _: statuses.append(status)))
    return statuses[0], json.loads(data)


def test_a_record_with_no_paths_is_refused_naming_every_changed_product_file(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = _clone(root=tmp_path)
    application, authority = _observer(tmp_path=tmp_path, monkeypatch=monkeypatch, clone=clone)
    authority.add(record=_record(clone=clone, paths={}, covered=()))
    status, result = _arm(application=application, clone=clone)
    reason = str(result.get("reason"))
    facts = [
        status == "403 Forbidden",
        reason.startswith("incident-focused-evidence-paths-incomplete:"),
        all(name in reason for name in _PRODUCT),
        "README.md" not in reason,
        "tests/test_gadget.py" not in reason,
        "read-current" not in authority.actions,
    ]
    assert all(facts), (facts, status, result)


def test_a_record_missing_some_changed_product_files_lists_exactly_those(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = _clone(root=tmp_path)
    application, authority = _observer(tmp_path=tmp_path, monkeypatch=monkeypatch, clone=clone)
    paths = {"src/widget.py": "executable", "README.md": "non-executable"}
    authority.add(record=_record(clone=clone, paths=paths, covered=("src/widget.py",)))
    status, result = _arm(application=application, clone=clone)
    reason = str(result.get("reason"))
    facts = [
        status == "403 Forbidden",
        reason.startswith("incident-focused-evidence-paths-incomplete:"),
        "src/gadget.py" in reason,
        "src/doc_only.py" in reason,
        "src/widget.py" not in reason,
    ]
    assert all(facts), (facts, status, result)


def test_a_changed_executable_file_the_record_calls_non_executable_needs_a_coverage_row(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = _clone(root=tmp_path)
    application, authority = _observer(tmp_path=tmp_path, monkeypatch=monkeypatch, clone=clone)
    paths = {**_HONEST, "src/gadget.py": "non-executable"}
    authority.add(record=_record(clone=clone, paths=paths, covered=("src/widget.py",)))
    status, result = _arm(application=application, clone=clone)
    reason = str(result.get("reason"))
    facts = [
        status == "403 Forbidden",
        reason.startswith("incident-focused-evidence-coverage-absent:"),
        "src/gadget.py" in reason,
        "src/widget.py" not in reason,
        "src/doc_only.py" not in reason,
    ]
    assert all(facts), (facts, status, result)


def test_a_record_covering_every_changed_product_file_is_admitted(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = _clone(root=tmp_path)
    application, authority = _observer(tmp_path=tmp_path, monkeypatch=monkeypatch, clone=clone)
    authority.add(record=_record(clone=clone, paths=_HONEST, covered=_EXECUTABLE))
    status, result = _arm(application=application, clone=clone)
    facts = [
        (status, result.get("status")) == ("202 Accepted", "armed"),
        authority.actions[-1] == "read-current",
    ]
    assert all(facts), (facts, status, result)


@pytest.mark.parametrize("names_the_deletion", [True, False])
def test_a_head_deleting_a_product_file_is_judged_against_the_collectors_deleted_row(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, names_the_deletion: bool
) -> None:
    # The collector's `git diff --name-only` lists a deleted path and `classify`
    # names it "deleted", so an honest record carries it with no coverage row.
    clone = _clone(root=tmp_path, retired=True)
    application, authority = _observer(tmp_path=tmp_path, monkeypatch=monkeypatch, clone=clone)
    paths = {**_HONEST, _RETIRED: "deleted"} if names_the_deletion else _HONEST
    authority.add(record=_record(clone=clone, paths=paths, covered=_EXECUTABLE))
    status, result = _arm(application=application, clone=clone)
    reason = str(result.get("reason"))
    if names_the_deletion:
        facts = [(status, result.get("status")) == ("202 Accepted", "armed")]
    else:
        facts = [
            status == "403 Forbidden",
            reason.startswith("incident-focused-evidence-paths-incomplete:"),
            _RETIRED in reason,
        ]
    assert all(facts), (facts, status, result)


def test_the_changed_set_ignores_the_request_base_and_comes_from_the_clone(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = _clone(root=tmp_path)
    application, authority = _observer(tmp_path=tmp_path, monkeypatch=monkeypatch, clone=clone)
    authority.add(record=_record(clone=clone, paths={}, covered=()))
    status, result = _arm(application=application, clone=clone, base_sha=clone.head)
    reason = str(result.get("reason"))
    facts = [
        status == "403 Forbidden",
        reason.startswith("incident-focused-evidence-paths-incomplete:"),
        all(name in reason for name in _PRODUCT),
    ]
    assert all(facts), (facts, status, result)


@pytest.mark.parametrize(
    ("config", "target_ref", "drop_head", "detail"),
    [
        (_CONFIG, True, True, "reference clone does not hold head"),
        (_CONFIG, False, False, "merge base"),
        ("", True, False, "declares no source prefixes"),
        ("[tool.livespec_dev_tooling\n", True, False, "configuration"),
    ],
)
def test_a_changed_set_the_clone_cannot_establish_refuses_and_never_admits(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    config: str,
    target_ref: bool,
    drop_head: bool,
    detail: str,
) -> None:
    clone = _clone(root=tmp_path, config=config, target_ref=target_ref)
    if drop_head:
        _ = _git(repo=clone.repo, args=["update-ref", "-d", "refs/heads/master"])
        _ = _git(repo=clone.repo, args=["reflog", "expire", "--expire=now", "--all"])
        _ = _git(repo=clone.repo, args=["gc", "-q", "--prune=now"])
    application, authority = _observer(tmp_path=tmp_path, monkeypatch=monkeypatch, clone=clone)
    authority.add(record=_record(clone=clone, paths=_HONEST, covered=_EXECUTABLE))
    status, result = _arm(application=application, clone=clone)
    reason = str(result.get("reason"))
    facts = [
        status == "403 Forbidden",
        reason.startswith("incident-focused-evidence-changes-unavailable:"),
        detail in reason,
        "read-current" not in authority.actions,
    ]
    assert all(facts), (facts, status, result)
