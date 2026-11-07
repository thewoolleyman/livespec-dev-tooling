"""Records at the trusted independent incident observer boundary."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "JobCallback",
    "LeafCompletion",
    "ObserverArm",
    "ObserverArmQuery",
    "ObserverRegistration",
    "ObserverResult",
    "RecoveryIntent",
    "RegressionReopen",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


@dataclass(frozen=True, kw_only=True)
class JobCallback:
    """Raw request and delivery headers from the independently hosted endpoint."""

    body: bytes
    signature: str
    event: str
    delivery_id: str


@dataclass(frozen=True, kw_only=True)
class ObserverArm:
    """Durable readiness BEFORE a merge, when no master run exists yet."""

    repository: str
    incident_item_id: str
    attempt_id: str
    operation_id: str
    generation: int
    owner: str
    phase: str
    pr_number: int
    base_sha: str
    head_sha: str
    required_jobs: tuple[str, ...]
    controller_release: str
    controller_revision: str
    authority_receipt: bytes


@dataclass(frozen=True, kw_only=True)
class ObserverArmQuery:
    """Exact PR and canonical receipt identity queried by the merge entrance."""

    repository: str
    arm_id: str
    pr_number: int
    base_sha: str
    head_sha: str
    receipt_digest: str


@dataclass(frozen=True, kw_only=True)
class LeafCompletion:
    """One signature-verified completed job, before workflow completion."""

    delivery_id: str
    repository: str
    head_sha: str
    branch: str
    run_id: int
    job_id: int
    job_name: str
    conclusion: str


@dataclass(frozen=True, kw_only=True)
class ObserverRegistration:
    """A trusted exact-master binding, never ambient JSON authority.

    Standalone admission calls the canonical current reader. A pre-merge arm
    instead grants exact later merge/run binding without a fresh tenant call;
    its original canonical receipt and identity stay unchanged. Observed merge
    data are effect receipts, not a new canonical lifecycle. Correction must
    advance the independent fence before new effects.
    """

    repository: str
    incident_item_id: str
    attempt_id: str
    operation_id: str
    generation: int
    owner: str
    phase: str
    head_sha: str
    run_id: int
    required_jobs: tuple[str, ...]
    controller_release: str
    controller_revision: str
    candidate_revision: str
    authority_receipt: bytes
    branch: str = "master"


@dataclass(frozen=True, kw_only=True)
class RegressionReopen:
    """The canonically verified `reverting` generation that reopened a landed attempt.

    An authenticated `/recover` retains this instead of a leaf completion: a
    related regression seen on another PR or on master reopened the same
    incident, and the current reader confirmed the generation and its exact
    receipt bytes (`receipt_digest`) before the observer persisted the action.
    """

    attempt_id: str
    operation_id: str
    generation: int
    owner: str
    receipt_digest: str


@dataclass(frozen=True, kw_only=True)
class RecoveryIntent:
    """Immutable action identity persisted before recovery authority is called.

    Exactly one cause is set: the failing registered master leaf
    (``completion``) or a verified regression reopen (``regression``). Both
    key the same registration action id, so one landed attempt has one revert.
    """

    action_id: str
    registration: ObserverRegistration
    completion: LeafCompletion | None = None
    observer_arm: ObserverArm | None = None
    regression: RegressionReopen | None = None


@dataclass(frozen=True, kw_only=True)
class ObserverResult:
    """Explicit action disposition; unresolved never grants retry permission."""

    status: str
    reason: str
    action_id: str | None = None
    receipt: str | None = None
