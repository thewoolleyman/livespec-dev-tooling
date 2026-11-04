"""Immutable incident operation records shared by resolution and transport."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.result import Result  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = [
    "ExecutionContext",
    "ExecutionMode",
    "IncidentConfigurationRefusal",
    "IncidentResolution",
    "Invocation",
    "OperationIdentity",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-sh3vz3


class ExecutionMode:
    """The only execution modes an incident-aware caller may select."""

    NORMAL = "normal"
    EXPEDITED_REPAIR = "expedited-repair"
    EMERGENCY_REVERT = "emergency-revert"


class Invocation:
    """Trusted origin context, which takes precedence over ambient variables."""

    ORDINARY = "ordinary"
    NORMAL_MASTER = "normal-master"
    NORMAL_FACTORY_FOLLOW_UP = "normal-factory-follow-up"


@dataclass(frozen=True, kw_only=True)
class OperationIdentity:
    """The immutable identity bound to one incident operation."""

    incident_item_id: str
    attempt_id: str
    phase: str
    repository: str
    base_sha: str
    head_sha: str
    operation_id: str
    recorded_incident_merge_sha: str | None = None


@dataclass(frozen=True, kw_only=True)
class ExecutionContext:
    """One resolved mode and its identity, ready for gate selection."""

    mode: str
    invocation: str
    identity: OperationIdentity | None


@dataclass(frozen=True, kw_only=True)
class IncidentConfigurationRefusal:
    """A named, expected refusal that must not be mistaken for normal mode."""

    code: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class IncidentResolution:
    """Result-backed resolution with an ergonomic boundary-facing inspection API."""

    result: Result[ExecutionContext, IncidentConfigurationRefusal]

    @property
    def is_successful(self) -> bool:
        """Whether resolving the trusted operation context succeeded."""
        return is_successful(self.result)

    def unwrap(self) -> ExecutionContext:
        """Return the resolved context after a caller has checked success."""
        return self.result.unwrap()

    def failure(self) -> IncidentConfigurationRefusal:
        """Return the named refusal after a caller has checked failure."""
        return self.result.failure()
