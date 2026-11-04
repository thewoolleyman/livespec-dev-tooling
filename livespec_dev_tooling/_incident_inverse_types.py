"""Explicit immutable scope, plans and scoped forge boundary for incident inverses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livespec_dev_tooling._incident_observer_types import RecoveryIntent

__all__: list[str] = [
    "InverseConflictRequest",
    "InverseForge",
    "InversePlan",
    "InversePublishRequest",
    "InversePublishResult",
    "InverseRefusal",
    "LandedIncident",
    "RecoveryOutcome",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-lgfo3v


@dataclass(frozen=True, kw_only=True)
class LandedIncident:
    """Complete observed forge scope bound to the original armed authority bytes.

    The trusted forge adapter authenticates the exact armed PR/base/head and
    full landed chain. A terminal merge alone is never a complete receipt.
    """

    repository: str
    pr_number: int
    original_base_sha: str
    original_head_sha: str
    before_sha: str
    merge_sha: str
    landed_commits: tuple[str, ...]
    landed_trees: tuple[str, ...]
    patch_sha256: str
    changed_paths: tuple[str, ...]
    authority_sha256: str


@dataclass(frozen=True, kw_only=True)
class InversePlan:
    """The whole inverse tree computed against one exact current master head."""

    scope: LandedIncident
    expected_head: str
    tree_sha: str
    inverse_patch: bytes


@dataclass(frozen=True, kw_only=True)
class InverseRefusal:
    """A named inability to construct or authorize a complete inverse."""

    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class InversePublishRequest:
    """A scoped principal's entire-tree expected-master-head CAS request."""

    intent: RecoveryIntent
    plan: InversePlan
    message: str


@dataclass(frozen=True, kw_only=True)
class InversePublishResult:
    """Committed, definite head movement, or an unknown effect that must not retry."""

    status: str
    merge_sha: str | None = None
    tree_sha: str | None = None


@dataclass(frozen=True, kw_only=True)
class InverseConflictRequest:
    """An owned conflict effect receipt, persisted before acknowledging recovery."""

    intent: RecoveryIntent
    scope: LandedIncident
    expected_head: str
    reason: str
    receipt: str


@dataclass(frozen=True, kw_only=True)
class RecoveryOutcome:
    """Recovery disposition; a missing receipt leaves the observer intent pending."""

    status: str
    reason: str
    receipt: str | None = None


class InverseForge(Protocol):
    """Independently provisioned, authenticated recovery service, never ambient flags.

    publish_inverse MUST atomically compare master itself, use only the scoped
    principal, and never wait for tests, factory or CI. Lookup is by exact action
    id, including effects whose original response was lost. authorize_inverse
    binds the immutable observer arm, complete scope and principal capability.
    No production implementation or capability is implied by this interface.
    """

    def landed_incident(self, *, intent: RecoveryIntent) -> LandedIncident | None: ...
    def authorize_inverse(self, *, intent: RecoveryIntent, scope: LandedIncident) -> bool: ...
    def read_master_head(self, *, repository: str, branch: str) -> str: ...
    def read_exact_receipt(self, *, intent: RecoveryIntent) -> str | None:
        """Return a recorded receipt, or None ONLY on definitive no-effect absence.

        Unavailable, malformed or reserved/unknown state MUST raise OSError;
        an implementation must never conflate it with authoritative absence.
        """
        ...

    def publish_inverse(self, *, request: InversePublishRequest) -> InversePublishResult: ...
    def record_conflict(self, *, request: InverseConflictRequest) -> str | None: ...
