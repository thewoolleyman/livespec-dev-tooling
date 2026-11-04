"""Serialization for full pre-commit aggregate evidence in a green token."""

from __future__ import annotations

import datetime
import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple, cast

import structlog

__all__: list[str] = [
    "NORMAL_VALIDATION",
    "PreCommitAggregateEvidence",
    "ValidationScope",
    "index_tree_hash",
    "is_normal_validation",
    "load_tree_hash",
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


@dataclass(frozen=True, kw_only=True)
class ValidationScope:
    """Caller-resolved validation provenance, separate from incident authority."""

    mode: str = "normal"
    scope: str = "full-suite"


NORMAL_VALIDATION = ValidationScope()


# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-xluwqj
def is_normal_validation(*, mode: object = "normal", scope: object = "full-suite") -> bool:
    """Partial incident proof cannot be consumed or minted as full normal validation."""
    return mode == "normal" and scope == "full-suite"


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


def serialize_evidence(
    *, evidence: PreCommitAggregateEvidence, validation: ValidationScope = NORMAL_VALIDATION
) -> str:
    """Return a green-token document retaining the aggregate's provenance."""
    if not is_normal_validation(mode=validation.mode, scope=validation.scope):
        message = "normal full-suite evidence required"
        raise ValueError(message)
    return json.dumps(
        {
            "mode": "normal",
            "scope": "full-suite",
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
        record = cast("dict[str, object]", token)
        if not is_normal_validation(
            mode=record.get("mode", "normal"), scope=record.get("scope", "full-suite")
        ):
            return None
        raw = record.get("pre_commit_aggregate")
        fields = cast("dict[str, object]", raw)
        if not is_normal_validation(
            mode=fields.get("mode", "normal"), scope=fields.get("scope", "full-suite")
        ):
            return None
        values = tuple(fields[name] for name in PreCommitAggregateEvidence._fields)
    except (AttributeError, KeyError, TypeError, json.JSONDecodeError):
        return None
    if not all(isinstance(value, str) and value for value in values):
        return None
    return PreCommitAggregateEvidence(*cast("tuple[str, str, str, str]", values))


def write_evidence(
    *,
    path: Path,
    tree_hash: str,
    run_id: str,
    output_checksum: str,
    validation: ValidationScope = NORMAL_VALIDATION,
) -> PreCommitAggregateEvidence:
    """Write named aggregate evidence and return the values persisted."""
    evidence = PreCommitAggregateEvidence(
        tree_hash=tree_hash,
        run_id=run_id,
        output_checksum=output_checksum,
        captured_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    _ = path.write_text(
        serialize_evidence(evidence=evidence, validation=validation), encoding="utf-8"
    )
    return evidence


def persist_pre_commit_evidence(
    *,
    path: Path,
    tree_hash: str,
    log: structlog.stdlib.BoundLogger,
    run_id: str,
    output_checksum: str,
    validation: ValidationScope = NORMAL_VALIDATION,
) -> int:
    """Persist evidence without making a successful pre-commit aggregate fail."""
    if not is_normal_validation(mode=validation.mode, scope=validation.scope):
        log.warning("pre-commit evidence refused: normal full-suite evidence required")
        return 1
    try:
        evidence = write_evidence(
            path=path,
            tree_hash=tree_hash,
            run_id=run_id,
            output_checksum=output_checksum,
            validation=validation,
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


def load_tree_hash(
    *, token_path: Callable[[], Path], log: structlog.stdlib.BoundLogger
) -> str | None:
    """Read and validate the stored tree hash from the token file.

    Returns the stored tree-hash string on success, or None when the
    token is absent, unreadable, or malformed (each case is logged).
    """
    try:
        path = token_path()
        raw = path.read_text(encoding="utf-8")
        token: object = json.loads(raw)
    except FileNotFoundError:
        log.info(
            "green token check: no token found (cold path); running full aggregate",
        )
        return None
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as exc:
        log.info(
            "green token check: token unreadable; running full aggregate",
            error=str(exc),
        )
        return None
    # A token whose JSON root is not an object is malformed rather than
    # unreadable, so it joins the missing-field case below on one report path.
    stored: object = None
    if isinstance(token, dict):
        record = cast("dict[str, object]", token)
        # EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-xluwqj
        if not is_normal_validation(
            mode=record.get("mode", "normal"), scope=record.get("scope", "full-suite")
        ):
            log.info("green token check: partial evidence refused; running full aggregate")
            return None
        stored = record.get("tree_hash")
    if not isinstance(stored, str):
        log.info(
            "green token check: invalid token format; running full aggregate",
        )
        return None
    return stored
