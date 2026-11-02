"""Tests for serializable full pre-commit aggregate evidence."""

from __future__ import annotations

import importlib
from pathlib import Path

import structlog

__all__: list[str] = []

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "_green_token_evidence.py"


def test_pre_commit_evidence_round_trips_only_when_complete() -> None:
    """Suite-green may reuse only complete, named aggregate evidence."""
    assert _MODULE_PATH.is_file()
    module = importlib.import_module("livespec_dev_tooling._green_token_evidence")
    evidence = module.PreCommitAggregateEvidence(
        tree_hash="same-tree",
        run_id="pre-commit-aggregate:run-123",
        output_checksum="sha256:aggregate-output",
        captured_at="2026-11-02T12:00:00Z",
    )
    assert module.read_evidence_text(text=module.serialize_evidence(evidence=evidence)) == evidence
    assert module.read_evidence_text(text='{"pre_commit_aggregate": {}}') is None
    assert (
        module.read_evidence_text(
            text=(
                '{"pre_commit_aggregate": {"tree_hash": "same-tree", '
                '"run_id": "pre-commit-aggregate:run-123", '
                '"output_checksum": "", "captured_at": "2026-11-02T12:00:00Z"}}'
            )
        )
        is None
    )


def test_pre_commit_evidence_persistence_is_advisory(tmp_path: Path) -> None:
    """An evidence-write fault must not turn a passing aggregate into a refusal."""
    module = importlib.import_module("livespec_dev_tooling._green_token_evidence")
    token_path = tmp_path / "token.json"

    assert (
        module.persist_pre_commit_evidence(
            path=token_path,
            tree_hash="same-tree",
            log=structlog.get_logger(),
            run_id="pre-commit-aggregate:run-123",
            output_checksum="sha256:aggregate-output",
        )
        == 0
    )
    assert module.read_evidence(path=token_path) is not None
    assert module.read_evidence(path=tmp_path / "missing.json") is None
