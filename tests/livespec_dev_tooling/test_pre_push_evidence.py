"""Unit tests for `livespec_dev_tooling/_pre_push_evidence.py`."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from livespec_dev_tooling._pre_push_evidence import (
    both_delegated_keys,
    clear_evidence,
    read_evidence,
    write_evidence,
)

__all__: list[str] = []


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("delegated_gate = true\ndelegated_pre_commit = true\n", True),
        ("delegated_gate = true\n", False),
        ("delegated_pre_commit = true\n", False),
        ("delegated_gate = true\ndelegated_pre_commit = false\n", False),
        ('delegated_gate = true\ndelegated_pre_commit = "yes"\n', False),
    ],
    ids=["both", "gate-only", "pre-commit-only", "pre-commit-false", "malformed"],
)
def test_both_delegated_keys_requires_both_literal_trues(
    *, tmp_path: Path, body: str, expected: bool
) -> None:
    """Only the literal boolean `true` on BOTH keys selects the both-keys behaviour."""
    _ = (tmp_path / "pyproject.toml").write_text(
        f"[tool.livespec_dev_tooling]\n{body}", encoding="utf-8"
    )

    assert both_delegated_keys(repo_root=tmp_path) is expected


def test_written_evidence_reads_back_whole(*, tmp_path: Path) -> None:
    """The record names the tree, the gate Job in its own field, and the members."""
    path = tmp_path / "evidence.json"

    written = write_evidence(
        path=path, tree_hash="a" * 40, gate_job="gate-x", members_passed=("check-a", "check-b")
    )

    assert read_evidence(path=path) == written
    assert json.loads(path.read_text(encoding="utf-8"))["gate_job"] == "gate-x"


@pytest.mark.parametrize(
    "document",
    [
        "{not json",
        "[]",
        json.dumps({"tree_hash": "t", "members_passed": [], "captured_at": "c"}),
        json.dumps({"tree_hash": "t", "gate_job": "", "members_passed": [], "captured_at": "c"}),
        json.dumps({"tree_hash": "t", "gate_job": "j", "members_passed": "a", "captured_at": "c"}),
        json.dumps({"tree_hash": "t", "gate_job": "j", "members_passed": [1], "captured_at": "c"}),
    ],
    ids=["malformed", "not-an-object", "no-job", "empty-job", "members-not-list", "bad-member"],
)
def test_an_incomplete_record_is_no_evidence(*, tmp_path: Path, document: str) -> None:
    """A record without a gate Job name, or one that cannot be read whole, never qualifies."""
    path = tmp_path / "evidence.json"
    _ = path.write_text(document, encoding="utf-8")

    assert read_evidence(path=path) is None


def test_an_absent_record_is_no_evidence_and_clearing_it_is_harmless(*, tmp_path: Path) -> None:
    """Clearing removes a record, and clearing nothing is not an error."""
    path = tmp_path / "evidence.json"
    assert read_evidence(path=path) is None
    _ = write_evidence(path=path, tree_hash="a" * 40, gate_job="gate-x", members_passed=())

    clear_evidence(path=path)
    clear_evidence(path=path)

    assert not path.exists()
