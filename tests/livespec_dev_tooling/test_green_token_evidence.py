"""Tests for the serializable pre-commit evidence inside a green token."""

from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess

import pytest
import structlog

import livespec_dev_tooling._green_token_evidence as evidence_module
from livespec_dev_tooling._green_token_evidence import (
    PreCommitAggregateEvidence,
    index_tree_hash,
    persist_pre_commit_evidence,
    read_evidence,
    serialize_evidence,
)
from livespec_dev_tooling.checks._red_green_replay_suite import staged_tree_hash

__all__: list[str] = []


def test_evidence_round_trips_and_rejects_malformed_records(tmp_path: Path) -> None:
    """Only a complete named aggregate verdict can be reused by suite-green."""
    evidence = PreCommitAggregateEvidence(
        tree_hash="same-tree",
        run_id="pre-commit-aggregate:run-123",
        output_checksum="sha256:aggregate-output",
        captured_at="2026-11-02T12:00:00Z",
    )
    token_path = tmp_path / "token.json"
    token_path.write_text(serialize_evidence(evidence=evidence), encoding="utf-8")

    assert read_evidence(path=token_path) == evidence
    token_path.write_text('{"pre_commit_aggregate": {"tree_hash": "same-tree"}}', encoding="utf-8")
    assert read_evidence(path=token_path) is None
    token_path.write_text(
        (
            '{"pre_commit_aggregate": {"tree_hash": "same-tree", '
            '"run_id": "pre-commit-aggregate:run-123", '
            '"output_checksum": "", "captured_at": "2026-11-02T12:00:00Z"}}'
        ),
        encoding="utf-8",
    )
    assert read_evidence(path=token_path) is None


def test_index_tree_hash_and_persistence_are_advisory(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The pre-commit writer records its index tree without risking the aggregate."""

    def git_write_tree(*args: object, **kwargs: object) -> CompletedProcess[str]:
        _ = args, kwargs
        return CompletedProcess(args=["git", "write-tree"], returncode=0, stdout="same-tree\n")

    def failed_write(**kwargs: object) -> PreCommitAggregateEvidence:
        _ = kwargs
        raise OSError("unavailable")

    assert staged_tree_hash(cwd=tmp_path) is None
    monkeypatch.setattr(evidence_module.subprocess, "run", git_write_tree)
    assert index_tree_hash(cwd=tmp_path) == "same-tree"

    token_path = tmp_path / "token.json"
    assert (
        persist_pre_commit_evidence(
            path=token_path,
            tree_hash="same-tree",
            log=structlog.get_logger(),
            run_id="pre-commit-aggregate:run-123",
            output_checksum="sha256:aggregate-output",
        )
        == 0
    )
    assert read_evidence(path=token_path) is not None
    monkeypatch.setattr(evidence_module, "write_evidence", failed_write)
    assert (
        persist_pre_commit_evidence(
            path=token_path,
            tree_hash="same-tree",
            log=structlog.get_logger(),
            run_id="pre-commit-aggregate:run-123",
            output_checksum="sha256:aggregate-output",
        )
        == 0
    )
