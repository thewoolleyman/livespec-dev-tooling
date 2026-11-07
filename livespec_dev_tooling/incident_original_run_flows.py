"""Collect a reverted incident's completed original master run; propose its correction.

The flows behind `python -m livespec_dev_tooling.incident_original_run_entry`.
The original identity comes from the controller's retained registration and
the canonical attempt history, never from the caller. GRAPH.json lists every
expected job as `{"name": ..., "needs": [...]}`, spelled as the forge names the
jobs, and must cover every job the registration watched. The repair digest of a
proposal is measured from Git here, so a reland whose change is unchanged from
the reverted attempt cannot claim a repair.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_original_run_canonical import (
    EVIDENCE_MARKER,
    CanonicalPorts,
    CorrectionTarget,
    authority_query,
    canonical_adapter,
    recorded_digests,
)
from livespec_dev_tooling._incident_original_run_codec import decode_evidence
from livespec_dev_tooling._incident_run_types import (
    CorrectedAttempt,
    EvidenceRefusal,
    ExpectedJob,
    OriginalRun,
    RunEvidence,
    RunSnapshot,
)
from livespec_dev_tooling.incident_run_collector import OriginalRunCollector
from livespec_dev_tooling.incident_run_evidence import evidence_digest

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["Collection", "Correction", "EntryPorts", "GitPort", "collect", "propose"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zvntys
_REFUSED = 78
_NOT_A_REVERT = "the revert does not descend from the original merge"
_MISMATCHED = "retained evidence names another original run"
_CORRECTED_FROM = "collecting-failures"
# The canonical writer derives the corrected attempt's id; this only differs
# from the original so the local proposal gate can run.
_ASSIGNED = "assigned-by-canonical-writer"

GitPort = Callable[[Sequence[str], bytes], bytes]
RunReader = Callable[[OriginalRun], RunSnapshot | EvidenceRefusal]


@dataclass(frozen=True, kw_only=True)
class EntryPorts:
    canonical: CanonicalPorts
    git: GitPort
    read: RunReader


@dataclass(frozen=True, kw_only=True)
class Collection:
    state_dir: Path
    repository: str
    revert_sha: str
    expected: tuple[ExpectedJob, ...]
    run_attempt: int = 1
    workflow_path: str = ".github/workflows/ci.yml"


@dataclass(frozen=True, kw_only=True)
class Correction:
    state_dir: Path
    repository: str
    evidence_digest: str
    next_head_sha: str
    target_ref: str
    current_attempt: str
    current_owner: str
    current_generation: int
    resolved_jobs: tuple[tuple[str, str], ...] = ()
    base_ref: str = "origin/master"


def _refuse(*, code: str, detail: str) -> EvidenceRefusal:
    return EvidenceRefusal(code="incident-original-run-" + code, detail=detail)


@impure_safe
def _registration(*, state_dir: Path, repository: str) -> ObserverRegistration:
    with repository_lock(directory=state_dir, repository=repository) as path:
        registration = read_registration(record=load_record(path=path))
    if registration is None or registration.repository != repository:
        raise LookupError(repository)
    return registration


@impure_safe
def _pr_number(*, ports: EntryPorts, registration: ObserverRegistration) -> int:
    result = ports.canonical.authority(
        "read-history", authority_query(registration=registration), {}
    )
    attempt = result.get("attempt")
    number = (
        cast("dict[str, object]", attempt).get("pr_number") if isinstance(attempt, dict) else None
    )
    if type(number) is not int:
        raise TypeError(registration.incident_item_id)
    return number


def _text(*, git: GitPort, args: Sequence[str]) -> str:
    return git(args, b"").decode().strip()


@impure_safe
def _original(
    *, request: Collection, registration: ObserverRegistration, pr_number: int, git: GitPort
) -> OriginalRun:
    merge = registration.head_sha
    if request.revert_sha == merge:
        raise ValueError(_NOT_A_REVERT)
    _ = git(["merge-base", "--is-ancestor", merge, request.revert_sha], b"")
    source = git(["cat-file", "blob", f"{merge}:{request.workflow_path}"], b"")
    return OriginalRun(
        repository=registration.repository,
        item_id=registration.incident_item_id,
        attempt_id=registration.attempt_id,
        operation_id=registration.operation_id,
        generation=registration.generation,
        owner=registration.owner,
        pr_number=pr_number,
        merge_sha=merge,
        tree_sha=_text(git=git, args=["rev-parse", "--verify", merge + "^{tree}"]),
        revert_sha=request.revert_sha,
        run_id=registration.run_id,
        run_attempt=request.run_attempt,
        workflow_path=request.workflow_path,
        graph_revision=merge,
        graph_digest=hashlib.sha256(source).hexdigest(),
        expected=request.expected,
    )


@dataclass(frozen=True, kw_only=True)
class _CompletedOnly:
    """The forge read, refused by name until the original run has completed."""

    read: RunReader

    def __call__(self, original: OriginalRun) -> RunSnapshot | EvidenceRefusal:
        snapshot = self.read(original)
        if isinstance(snapshot, RunSnapshot) and snapshot.status != "completed":
            detail = f"original run {original.run_id} is {snapshot.status}; receipts retained"
            return _refuse(code="in-progress", detail=detail)
        return snapshot


def collect(*, request: Collection, ports: EntryPorts) -> RunEvidence | EvidenceRefusal:
    """Collect the registered original run once it is complete, or refuse by name."""
    found = _registration(state_dir=request.state_dir, repository=request.repository)
    if not is_successful(found):
        return _refuse(code="unregistered", detail="no retained original-run registration")
    registration = unsafe_perform_io(found.unwrap())
    missing = sorted(set(registration.required_jobs) - {job.name for job in request.expected})
    if missing:
        return _refuse(code="graph-invalid", detail="expected graph omits " + ", ".join(missing))
    number = _pr_number(ports=ports, registration=registration)
    if not is_successful(number):
        return _refuse(code="authority-refused", detail="canonical attempt history unavailable")
    original = _original(
        request=request,
        registration=registration,
        pr_number=unsafe_perform_io(number.unwrap()),
        git=ports.git,
    )
    if not is_successful(original):
        return _refuse(code="local-revision", detail="merge, revert or workflow does not resolve")
    collector = OriginalRunCollector(
        directory=request.state_dir,
        read=_CompletedOnly(read=ports.read),
        canonical=canonical_adapter(ports=ports.canonical, registration=registration),
    )
    return collector.collect(
        original=unsafe_perform_io(original.unwrap()),
        continuation_id=f"original-run:{registration.run_id}:{request.run_attempt}",
    )


@impure_safe
def _retained(*, request: Correction, registration: ObserverRegistration) -> RunEvidence:
    with repository_lock(directory=request.state_dir, repository=request.repository) as path:
        stored = load_record(path=path).get("original_run_evidence")
    value = cast("dict[str, object]", stored)[request.evidence_digest]
    evidence = decode_evidence(value=value)
    original = evidence.original
    if evidence_digest(evidence=evidence) != request.evidence_digest or (
        original.item_id,
        original.attempt_id,
        original.run_id,
    ) != (registration.incident_item_id, registration.attempt_id, registration.run_id):
        raise ValueError(_MISMATCHED)
    return evidence


def _patch_id(*, git: GitPort, diff: bytes) -> str:
    return git(["patch-id", "--stable"], diff).decode().split(" ", 1)[0]


@impure_safe
def _measure(*, git: GitPort, original: OriginalRun, request: Correction) -> tuple[str, str, str]:
    """Base, staged tree and repair digest; the digest is empty for the reverted change."""
    head = request.next_head_sha
    base = _text(git=git, args=["merge-base", request.base_ref, head])
    _ = git(["merge-base", "--is-ancestor", original.revert_sha, base], b"")
    tree = _text(git=git, args=["rev-parse", "--verify", head + "^{tree}"])
    proposed = git(["diff", "--binary", base, head], b"")
    reverted = git(["diff", "--binary", original.revert_sha, original.revert_sha + "^"], b"")
    unchanged = not proposed.strip() or _patch_id(git=git, diff=proposed) == _patch_id(
        git=git, diff=reverted
    )
    return base, tree, "" if unchanged else hashlib.sha256(proposed).hexdigest()


def _current_query(*, registration: ObserverRegistration, request: Correction) -> dict[str, object]:
    """The attempt a recorded revert receipt moved to `collecting-failures`.

    `reopen-regression` records a new `recovery-<digest>` attempt under the
    incident principal, so the current attempt and owner differ from the
    original registration's and are named by the operator.
    """
    return {
        "repository": registration.repository,
        "item": registration.incident_item_id,
        "attempt": request.current_attempt,
        "phase": _CORRECTED_FROM,
        "operation": f"{request.current_attempt}#{_CORRECTED_FROM}",
        "generation": request.current_generation,
        "owner": request.current_owner,
    }


def propose(*, request: Correction, ports: EntryPorts) -> str | EvidenceRefusal:
    """Hand a correction proposal over collected evidence to the canonical writer."""
    found = _registration(state_dir=request.state_dir, repository=request.repository)
    if not is_successful(found):
        return _refuse(code="unregistered", detail="no retained original-run registration")
    registration = unsafe_perform_io(found.unwrap())
    retained = _retained(request=request, registration=registration)
    if not is_successful(retained):
        return _refuse(code="evidence-missing", detail="no retained evidence for this digest")
    evidence = unsafe_perform_io(retained.unwrap())
    recorded = impure_safe(recorded_digests)(ports=ports.canonical, original=evidence.original)
    if not is_successful(recorded) or request.evidence_digest not in unsafe_perform_io(
        recorded.unwrap()
    ):
        return _refuse(code="unrecorded", detail="evidence is not recorded on the incident item")
    measured = _measure(git=ports.git, original=evidence.original, request=request)
    if not is_successful(measured):
        return _refuse(code="local-revision", detail="corrected head does not build on the revert")
    base, tree, repair = unsafe_perform_io(measured.unwrap())
    target = CorrectionTarget(
        query=_current_query(registration=registration, request=request),
        base=base,
        staged_tree=tree,
        target_ref=request.target_ref,
    )
    proposal = CorrectedAttempt(
        original=evidence.original,
        evidence_digest=request.evidence_digest,
        classification_receipt=f"{EVIDENCE_MARKER}:{request.evidence_digest}",
        next_attempt_id=_ASSIGNED,
        next_head_sha=request.next_head_sha,
        repair_diff_digest=repair,
        resolved_jobs=request.resolved_jobs,
    )
    collector = OriginalRunCollector(
        directory=request.state_dir,
        read=ports.read,
        canonical=canonical_adapter(
            ports=ports.canonical, registration=registration, target=target
        ),
    )
    return collector.propose_correction(evidence=evidence, proposal=proposal)
