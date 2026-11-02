"""Serialization for full pre-commit aggregate evidence in a green token."""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import NamedTuple, cast

import structlog

__all__: list[str] = [
    "PreCommitAggregateEvidence",
    "index_tree_hash",
    "persist_pre_commit_evidence",
    "read_evidence",
    "read_evidence_text",
    "serialize_evidence",
    "write_evidence",
]


class PreCommitAggregateEvidence(NamedTuple):
    """A passed full pre-commit aggregate that may stand in for suite-green."""

    tree_hash: str
    run_id: str
    output_checksum: str
    captured_at: str


def index_tree_hash(*, cwd: Path) -> str:
    """Return the tree SHA that the pre-commit hook actually judged."""
    result = subprocess.run(  # noqa: S603
        ["git", "write-tree"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def serialize_evidence(*, evidence: PreCommitAggregateEvidence) -> str:
    """Return a green-token document retaining the aggregate's provenance."""
    return json.dumps(
        {
            "tree_hash": evidence.tree_hash,
            "pre_commit_aggregate": {
                "tree_hash": evidence.tree_hash,
                "run_id": evidence.run_id,
                "output_checksum": evidence.output_checksum,
                "captured_at": evidence.captured_at,
            },
        }
    )


def read_evidence_text(*, text: str) -> PreCommitAggregateEvidence | None:
    """Parse complete aggregate evidence, rejecting malformed or partial records."""
    try:
        token = json.loads(text)
        raw = cast("dict[str, object]", token).get("pre_commit_aggregate")
        fields = cast("dict[str, object]", raw)
        values = tuple(fields[name] for name in PreCommitAggregateEvidence._fields)
    except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if not all(isinstance(value, str) and value for value in values):
        return None
    return PreCommitAggregateEvidence(*cast("tuple[str, str, str, str]", values))


def write_evidence(
    *, path: Path, tree_hash: str, run_id: str, output_checksum: str
) -> PreCommitAggregateEvidence:
    """Write named aggregate evidence and return the values persisted."""
    evidence = PreCommitAggregateEvidence(
        tree_hash=tree_hash,
        run_id=run_id,
        output_checksum=output_checksum,
        captured_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    _ = path.write_text(serialize_evidence(evidence=evidence), encoding="utf-8")
    return evidence


def persist_pre_commit_evidence(
    *,
    path: Path,
    tree_hash: str,
    log: structlog.stdlib.BoundLogger,
    run_id: str,
    output_checksum: str,
) -> int:
    """Persist evidence without making a successful pre-commit aggregate fail."""
    try:
        evidence = write_evidence(
            path=path,
            tree_hash=tree_hash,
            run_id=run_id,
            output_checksum=output_checksum,
        )
        log.info(
            "pre-commit aggregate evidence written",
            tree_hash=evidence.tree_hash,
            run_id=evidence.run_id,
            path=str(path),
        )
    except OSError as exc:  # pragma: no cover
        log.warning("pre-commit aggregate evidence write failed; non-blocking", error=str(exc))
    return 0


def read_evidence(*, path: Path) -> PreCommitAggregateEvidence | None:
    """Read valid full pre-commit evidence, or None when it cannot be established."""
    try:
        return read_evidence_text(text=path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return None
