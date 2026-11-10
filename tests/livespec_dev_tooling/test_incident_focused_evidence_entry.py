"""The focused-evidence entrance measures, records and publishes incident proof.

Each test drives the real collector against a real Git fixture. Only the
registered canonical authority process is replaced, by a recording fake that
answers the way the orchestrator's `incident-authority` protocol does.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest
import structlog

from livespec_dev_tooling import green_token
from livespec_dev_tooling import incident_focused_evidence_entry as module
from livespec_dev_tooling._green_token_evidence import read_evidence_text
from livespec_dev_tooling.incident_hook_entry import QUERY_ENV
from livespec_dev_tooling.incident_hook_process import canonical

_MANUAL = [
    "--procedure",
    "  call answer() from a REPL\n  twice  ",
    "--expected",
    "43, not 42",
    "--observed",
    "43 both times ",
    "--verdict",
    "passed",
]
_RECEIPT_KEYS = {"receipt_id", "hook", "tree", "mode", "evidence_kind", "exit_status", "results"}
_ROW_KEYS = {"name", "status", "reason", "returncode", "duration_seconds", "output"}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _repository(root: Path) -> tuple[str, str]:
    for args in (
        ("init", "-q"),
        ("config", "user.name", "Fixture"),
        ("config", "user.email", "fixture@example.org"),
        ("checkout", "-qb", "repair"),
        ("remote", "add", "origin", "https://github.com/owner/repo.git"),
    ):
        _ = _git(root, *args)
    _ = (root / ".gitignore").write_text(
        ".pytest_cache/\n__pycache__/\n.coverage\n.livespec-coverage-reuse-token\n"
    )
    _ = (root / "pyproject.toml").write_text(
        '[tool.livespec_dev_tooling]\nsource_trees = ["src"]\n'
    )
    (root / "src").mkdir()
    (root / "tests").mkdir()
    _ = (root / "src/widget.py").write_text("def answer():\n    return 42\n")
    _ = (root / "src/other.py").write_text("def other():\n    return 1\n")
    _ = (root / "tests/test_widget.py").write_text(
        "from src.widget import answer\ndef test_answer():\n    assert answer() == 42\n"
    )
    _ = (root / "tests/test_other.py").write_text(
        "from src.other import other\ndef test_other():\n    assert other() == 1\n"
    )
    _ = _git(root, "add", ".")
    _ = _git(root, "commit", "-qm", "baseline")
    base = _git(root, "rev-parse", "HEAD")
    _ = (root / "src/widget.py").write_text("def answer():\n    return 43\n")
    repaired_test = (
        "from src.other import other\nfrom src.widget import answer\n"
        "def test_answer():\n    assert answer() == 43\n    assert other() == 1\n"
    )
    _ = (root / "tests/test_widget.py").write_text(repaired_test)
    _ = _git(root, "add", ".")
    _ = _git(root, "commit", "-qm", "repair attempt")
    return base, _git(root, "rev-parse", "HEAD")


class _Authority:
    """Record every canonical call and answer as the registered process does."""

    def __init__(self, *, query: dict[str, Any], reading: dict[str, Any]) -> None:
        self.query = query
        self.reading = reading
        self.calls: list[dict[str, Any]] = []
        self.receipts: dict[str, dict[str, Any]] = {}
        self.corrupt = ""

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        assert kwargs["query"] == self.query
        action = kwargs["action"]
        tokens = {
            "committed_token_id": self.reading["committed_token_id"],
            "current_token_id": self.reading["current_token_id"],
        }
        checksum = "sha256:" + "b" * 64
        if action == "record-local-gates":
            receipt = json.loads(kwargs["receipt"])
            self.receipts[receipt["receipt_id"]] = receipt
            spoiled = "sha1:abc" if self.corrupt == "record" else checksum
            return {"receipt_id": receipt["receipt_id"], "checksum": spoiled, **tokens}
        if action == "read-local-gates":
            receipt = self.receipts.get(kwargs["receipt_id"])
            absent = receipt is None or self.corrupt == "lookup"
            return {
                "status": "absent" if absent else "recorded",
                "receipt_id": kwargs["receipt_id"],
                "receipt": receipt,
                "checksum": None if receipt is None else checksum,
                **tokens,
            }
        if action == "read-history":
            attempt = dict(self.reading["attempt"])
            attempt["head"] = "0" * 40 if self.corrupt == "history" else attempt["head"]
            return {**self.reading, "attempt": attempt}
        return self.reading

    def actions(self) -> list[str]:
        return [call["action"] for call in self.calls]


@pytest.fixture
def wired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, _Authority]:
    # The set is never empty, so the scrub runs on a host whose environment
    # carries none of these names (CI) as well as on one that does.
    stale = {
        "EXPEDITED_INCIDENT_RESPONSE_REVERT",
        *(
            key
            for key in os.environ
            if key.startswith(("GIT_", "EXPEDITED_", "LIVESPEC_INCIDENT_"))
        ),
    }
    for key in stale:
        monkeypatch.delenv(key, raising=False)
    base, head = _repository(tmp_path)
    query = {
        "repository": "owner/repo",
        "item": "incident-1",
        "attempt": "attempt-1",
        "phase": "repair",
        "operation": "operation-1",
        "generation": 1,
        "owner": "operator:alice",
    }
    reading = {
        "attempt": {
            "repository": "owner/repo",
            "item_id": "incident-1",
            "attempt_id": "attempt-1",
            "phase": "repair",
            "operation_id": "operation-1",
            "generation": 1,
            "owner": "operator:alice",
            "base": base,
            "head": head,
            "pr_number": 0,
            "original_paths": ["src/widget.py"],
            "landed_commits": [],
        },
        "committed_token_id": "closed-1",
        "current_token_id": "open-2",
        "is_current": True,
        "operation_ids": ["operation-1"],
    }
    authority = _Authority(query=query, reading=reading)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EXPEDITED_INCIDENT_RESPONSE", "1")
    monkeypatch.setenv(QUERY_ENV, canonical(value=query))
    monkeypatch.setattr(module, "invoke_authority", authority)
    return tmp_path, authority


def test_entrance_measures_changed_tests_and_touched_files_into_one_record(
    wired: tuple[Path, _Authority], capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 1: changed tests run, coverage is touched-only, identity names the tree."""
    root, _ = wired
    status = module.main(argv=_MANUAL)
    lines = capsys.readouterr().out.splitlines()
    record = json.loads(lines[0])["record"]
    assert {
        "status": status,
        "lines": len(lines),
        "outcome": record["outcome"],
        "tests": record["selection"]["tests"],
        "returncode": record["tests"]["returncode"],
        "coverage": sorted(record["coverage"]),
        "percent": record["coverage"]["src/widget.py"]["summary"]["percent_covered"],
        "item": record["identity"]["incident_item_id"],
        "attempt": record["identity"]["attempt_id"],
        "head": record["identity"]["head_sha"],
        "tree": record["tree_hash"],
    } == {
        "status": 0,
        "lines": 1,
        "outcome": "passed",
        "tests": ["tests/test_widget.py"],
        "returncode": 0,
        "coverage": ["src/widget.py"],
        "percent": 100,
        "item": "incident-1",
        "attempt": "attempt-1",
        "head": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
    }


@pytest.mark.usefixtures("wired")
def test_manual_reproduction_is_preserved_verbatim_beside_the_measurement(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """DoD 2: the operator's four manual fields survive byte for byte."""
    _ = module.main(argv=_MANUAL)
    record = json.loads(capsys.readouterr().out)["record"]
    assert record["manual"] == {
        "procedure": "  call answer() from a REPL\n  twice  ",
        "expected": "43, not 42",
        "observed": "43 both times ",
        "outcome": "passed",
    }


@pytest.mark.parametrize("missing", ["--procedure", "--expected", "--observed", "--verdict"])
def test_each_manual_field_is_required_and_nothing_is_published(
    wired: tuple[Path, _Authority], capsys: pytest.CaptureFixture[str], missing: str
) -> None:
    """DoD 2 and 4: an incomplete manual reproduction refuses before any authority call."""
    _, authority = wired
    index = _MANUAL.index(missing)
    status = module.main(argv=_MANUAL[:index] + _MANUAL[index + 2 :])
    err = capsys.readouterr().err
    assert (status, missing in err, "incident-evidence-refused" in err, authority.calls) == (
        78,
        True,
        True,
        [],
    )


def test_blank_manual_field_is_refused_by_the_collector(
    wired: tuple[Path, _Authority], capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 2 and 4: a present but blank observation is not a reproduction."""
    _, authority = wired
    argv = [*_MANUAL]
    argv[argv.index("--observed") + 1] = "   "
    status = module.main(argv=argv)
    err = capsys.readouterr().err
    assert (status, "manual reproduction is incomplete" in err, authority.actions()) == (
        78,
        True,
        ["read-current"],
    )


def test_record_is_published_through_the_canonical_authority_and_bound_to_history(
    wired: tuple[Path, _Authority], capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 3: one canonical receipt, read back exactly, bound to the attempt and head."""
    root, authority = wired
    _ = module.main(argv=_MANUAL)
    printed = json.loads(capsys.readouterr().out)
    (receipt,) = authority.receipts.values()
    (row,) = receipt["results"]
    published = authority.calls[2]["receipt"]
    assert {
        "actions": authority.actions(),
        "canonical": published == canonical(value=json.loads(published)),
        "keys": set(receipt),
        "row_keys": set(row),
        "hook": receipt["hook"],
        "mode": receipt["mode"],
        "kind": receipt["evidence_kind"],
        "tree": receipt["tree"],
        "exit": receipt["exit_status"],
        "row": (row["name"], row["status"], row["returncode"]),
        "fast": 0 <= row["duration_seconds"] < 60,
        "output": json.loads(row["output"]) == printed["record"],
        "publication": printed["publication"],
        "normal": printed["normal_factory_proof"],
    } == {
        "actions": [
            "read-current",
            "read-local-gates",
            "record-local-gates",
            "read-local-gates",
            "read-history",
        ],
        "canonical": True,
        "keys": _RECEIPT_KEYS,
        "row_keys": _ROW_KEYS,
        "hook": "pre-push",
        "mode": "expedited-repair",
        "kind": "expedited-local-partial",
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "exit": 0,
        "row": ("incident-focused-evidence", "passed", 0),
        "fast": True,
        "output": True,
        "publication": {
            "receipt_id": receipt["receipt_id"],
            "checksum": "sha256:" + "b" * 64,
            "item": "incident-1",
            "attempt": "attempt-1",
            "head": _git(root, "rev-parse", "HEAD"),
            "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        },
        "normal": False,
    }


def test_incomplete_evidence_is_published_as_a_failed_row(
    wired: tuple[Path, _Authority], capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 3: a deferred test makes the proof incomplete; it is still recorded, not hidden."""
    _, authority = wired
    argv = [
        *_MANUAL,
        "--related-test",
        "tests/test_other.py",
        "--related-reason",
        "exercises the module the repair imports",
        "--defer-test",
        "tests/test_widget.py=needs the live service",
    ]
    status = module.main(argv=argv)
    record = json.loads(capsys.readouterr().out)["record"]
    (receipt,) = authority.receipts.values()
    (row,) = receipt["results"]
    assert (
        status,
        record["outcome"],
        record["selection"]["tests"],
        receipt["exit_status"],
        row["status"],
        row["returncode"],
        "deferred test: tests/test_widget.py: needs the live service" in row["reason"],
    ) == (1, "incomplete", ["tests/test_other.py"], 1, "failed", 1, True)


def test_slow_passing_collection_is_recorded_as_a_deferred_timeout(
    wired: tuple[Path, _Authority], monkeypatch: pytest.MonkeyPatch
) -> None:
    """DoD 3: a passing record that took a minute or more is not claimed as a fast pass."""
    _, authority = wired
    monkeypatch.setattr(module, "monotonic", Mock(side_effect=[0.0, 61.0]))
    status = module.main(argv=_MANUAL)
    (receipt,) = authority.receipts.values()
    (row,) = receipt["results"]
    assert (status, receipt["exit_status"], row["status"], row["returncode"]) == (
        0,
        0,
        "deferred-timeout",
        None,
    )


@pytest.mark.parametrize(
    ("corrupt", "reason"),
    [
        ("record", "does not bind this record"),
        ("lookup", "does not read back exactly"),
        ("history", "does not show the attempt and head"),
    ],
)
def test_publication_that_does_not_read_back_is_refused(
    wired: tuple[Path, _Authority],
    capsys: pytest.CaptureFixture[str],
    corrupt: str,
    reason: str,
) -> None:
    """DoD 3: a write the authority cannot show back is a refusal, not a success."""
    _, authority = wired
    authority.corrupt = corrupt
    status = module.main(argv=_MANUAL)
    captured = capsys.readouterr()
    assert (status, reason in captured.err, captured.out) == (78, True, "")


@pytest.mark.parametrize(
    ("environment", "reason"),
    [
        ({"EXPEDITED_INCIDENT_RESPONSE": None}, "resolved expedited incident context required"),
        ({"EXPEDITED_INCIDENT_RESPONSE": "maybe"}, "malformed incident flag"),
        ({QUERY_ENV: None}, "exact canonical incident authority query required"),
    ],
)
def test_outside_a_resolved_incident_context_nothing_is_read_or_published(
    wired: tuple[Path, _Authority],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    environment: dict[str, str | None],
    reason: str,
) -> None:
    """DoD 4: no flag, a malformed flag or no canonical query refuses before authority."""
    _, authority = wired
    for name, value in environment.items():
        if value is None:
            monkeypatch.delenv(name)
        else:
            monkeypatch.setenv(name, value)
    status = module.main(argv=_MANUAL)
    captured = capsys.readouterr()
    assert (status, reason in captured.err, captured.out, authority.calls) == (78, True, "", [])


@pytest.mark.parametrize(
    ("extra", "untracked", "reason"),
    [
        (["--related-test", "tests/missing.py"], "", "explicit existing tests required"),
        (["--defer-test", "tests/test_widget.py"], "", "--defer-test takes PATH=REASON"),
        ([], "src/stray.py", "working tree must equal the exact staged or committed scope"),
    ],
)
def test_failed_collection_publishes_nothing(
    wired: tuple[Path, _Authority],
    capsys: pytest.CaptureFixture[str],
    extra: list[str],
    untracked: str,
    reason: str,
) -> None:
    """DoD 4: a collection that cannot be established refuses with its reason."""
    root, authority = wired
    if untracked:
        _ = (root / untracked).write_text("VALUE = 1\n")
    status = module.main(argv=[*_MANUAL, *extra])
    captured = capsys.readouterr()
    assert (
        status,
        reason in captured.err,
        captured.out,
        "record-local-gates" in authority.actions(),
    ) == (78, True, "", False)


def test_oversized_record_is_refused_before_publication(
    wired: tuple[Path, _Authority],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DoD 4: a record the authority would reject for size is refused here, unpublished."""
    _, authority = wired
    monkeypatch.setattr(module, "_MAX_RECEIPT_BYTES", 10)
    status = module.main(argv=_MANUAL)
    err = capsys.readouterr().err
    assert (status, "exceeds" in err, authority.actions()) == (78, True, ["read-current"])


def test_help_is_not_a_refusal(capsys: pytest.CaptureFixture[str]) -> None:
    status = module.main(argv=["--help"])
    assert (status, "--verdict" in capsys.readouterr().out) == (0, True)


def test_published_focused_record_is_not_normal_coverage_evidence(
    wired: tuple[Path, _Authority], capsys: pytest.CaptureFixture[str]
) -> None:
    """DoD 5: normal consumers on the same tree reject the record and keep their own data."""
    root, authority = wired
    _ = (root / ".coverage").write_bytes(b"normal-coverage-data")
    _ = (root / ".livespec-coverage-reuse-token").write_text("normal-reuse-token")
    status = module.main(argv=_MANUAL)
    printed = capsys.readouterr().out
    (receipt,) = authority.receipts.values()
    log = structlog.get_logger()
    assert {
        "status": status,
        "printed": read_evidence_text(text=printed),
        "receipt": read_evidence_text(text=json.dumps(receipt)),
        "row": read_evidence_text(text=receipt["results"][0]["output"]),
        "coverage": (root / ".coverage").read_bytes(),
        "reuse": (root / ".livespec-coverage-reuse-token").read_text(),
        "green": green_token.check_token(cwd=root, log=log),
        "pre_commit": green_token.read_pre_commit_evidence(cwd=root),
        "token_file": (root / ".git" / "livespec-green-token.json").exists(),
    } == {
        "status": 0,
        "printed": None,
        "receipt": None,
        "row": None,
        "coverage": b"normal-coverage-data",
        "reuse": "normal-reuse-token",
        "green": 1,
        "pre_commit": None,
        "token_file": False,
    }
