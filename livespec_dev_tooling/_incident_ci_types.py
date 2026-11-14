"""Immutable inputs and dispositions for trusted incident PR check selection."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from livespec_dev_tooling.incident_execution import ExecutionContext

__all__: list[str] = [
    "CiAggregate",
    "CiAuthority",
    "CiConditional",
    "CiDeferral",
    "CiEvent",
    "CiOutcome",
    "CiPlan",
    "CiTarget",
    "CiTrust",
]


@dataclass(frozen=True, kw_only=True)
class CiEvent:
    """An authenticated forge event, rather than inherited environment flags."""

    kind: str
    repository: str
    base_sha: str
    head_sha: str
    pr_number: int | None = None
    labels: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class CiTarget:
    """One (job, check slug) member of a released inventory, with artifact dependencies.

    `batch` is the declaring job. `conditional` marks a member of a job whose
    job-level `if:` names the triggering event or ref; the incident entrance
    never runs such a member, it lists it on a conditional-job line.
    """

    name: str
    classification: str
    batch: str = "direct"
    needs: tuple[str, ...] = ()
    produces: tuple[str, ...] = ()
    consumes: tuple[str, ...] = ()
    conditional: bool = False


@dataclass(frozen=True, kw_only=True)
class CiAuthority:
    """Exact current attempt plus an independently admitted premerge observer arm."""

    context: ExecutionContext
    generation: int
    owner: str
    pr_number: int
    receipt_digest: str
    observer_arm_id: str


@dataclass(frozen=True, kw_only=True)
class CiTrust:
    """Independently supplied authority readers, never candidate receipt parsing."""

    current: Callable[[CiAuthority], bool]
    observer: Callable[[CiAuthority, CiEvent], bool]
    incident_label: str = "expedited-incident-response"


@dataclass(frozen=True, kw_only=True)
class CiDeferral:
    name: str
    reason: str


@dataclass(frozen=True, kw_only=True)
class CiConditional:
    """A job whose `if:` the entrance does not evaluate: its members are listed, never run."""

    job: str
    names: tuple[str, ...]
    reason: str


@dataclass(frozen=True, kw_only=True)
class CiPlan:
    """A head-bound execution plan; omitted work is never a check's outcome."""

    event: CiEvent
    mode: str
    scope: str
    selected: tuple[CiTarget, ...]
    deferred: tuple[CiDeferral, ...]
    environment: tuple[tuple[str, str], ...]
    authority: CiAuthority | None
    incident_label: str
    attribution: tuple[tuple[str, tuple[str, ...]], ...] = ()
    conditional: tuple[CiConditional, ...] = ()
    # The plan-time enablement reading (livespec-dev-tooling-exdkra). It is recorded in the
    # plan but is not part of the plan identity the entrance rechecks.
    enablement: dict[str, Any] | None = field(default=None, compare=False)


@dataclass(frozen=True, kw_only=True)
class CiOutcome:
    name: str
    head_sha: str
    scope: str
    outcome: str


@dataclass(frozen=True, kw_only=True)
class CiAggregate:
    """The stable ci-green result exposes actual execution and every deferral."""

    head_sha: str
    scope: str
    passed: tuple[str, ...]
    failed: tuple[str, ...]
    missing: tuple[str, ...]
    deferred: tuple[CiDeferral, ...]
    context_name: str = "ci-green"
    attribution: tuple[tuple[str, tuple[str, ...]], ...] = ()
    conditional: tuple[CiConditional, ...] = ()

    @property
    def successful(self) -> bool:
        """Missing, cancelled or skipped selected work cannot satisfy the merge gate."""
        return bool(self.passed) and not self.failed and not self.missing
