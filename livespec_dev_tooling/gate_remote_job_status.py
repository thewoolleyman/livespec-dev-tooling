"""Decode the Job replies the delegated gate client receives from Kubernetes."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias, cast

from livespec_dev_tooling.gate_remote_invocation import GateStepFailed

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "COMPLETE_CONDITION",
    "Terminal",
    "created_job_name",
    "reported_time",
    "terminal_condition",
    "unreadable",
]

COMPLETE_CONDITION = "Complete"
_TERMINAL_CONDITION_TYPES = frozenset({COMPLETE_CONDITION, "Failed"})
_CONDITION_ASSERTED = "True"
_JobPayload: TypeAlias = Mapping[str, Mapping[str, object]]
_Conditions: TypeAlias = Sequence[Mapping[str, str]]


@dataclass(frozen=True, kw_only=True)
class Terminal:
    """A Job status that reported a terminal condition, and which one it reported."""

    condition: str
    status: Mapping[str, object]


def unreadable(*, step: str, argv: Sequence[str], detail: str) -> GateStepFailed:
    """One shape for a step whose COMMAND ran and whose ANSWER was unusable.

    `returncode=None` is the distinction this exists to keep, and it is why its
    callers share it rather than each spelling a refusal: the command did not
    fail, so there is no exit code to report — what failed is the read. Both
    reach `GATE_NO_VERDICT` and refuse the push, and both must, but only one of
    them is a cluster saying no.
    """
    return GateStepFailed(step=step, argv=tuple(argv), returncode=None, detail=detail)


def created_job_name(
    *, argv: Sequence[str], payload: str, step: str
) -> Result[str, GateStepFailed]:
    """The name the API server ASSIGNED this Job, read off the submit's answer.

    A FAILURE, never a fallback. The manifest carries `generateName` rather than
    `name`, so there is no name to fall back TO: the renderer's old derived name
    is exactly the value that made a re-gate impossible, and reinstating it here
    as a guess would put this run back to waiting on another run's Job — or on
    nothing at all. A submit whose answer cannot be read is therefore a step that
    did not complete, which reaches `GATE_NO_VERDICT` and refuses the push, and
    that is sound: the Job may well be running, but nothing left can find it.
    """
    try:
        parsed = cast("_JobPayload", json.loads(payload))
    except json.JSONDecodeError as error:
        return Failure(
            unreadable(step=step, argv=argv, detail=f"unreadable submit response: {error}")
        )
    assigned = parsed.get("metadata", {}).get("name")
    if isinstance(assigned, str) and assigned:
        return Success(assigned)
    return Failure(
        unreadable(
            step=step,
            argv=argv,
            detail="the submit response carries no metadata.name for the created Job",
        )
    )


def reported_time(*, status: Mapping[str, object], key: str) -> str:
    """Return a Job clock reading, or an empty string when the Job omitted it."""
    reading = status.get(key)
    return reading if isinstance(reading, str) else ""


def terminal_condition(
    *, argv: Sequence[str], payload: str, step: str
) -> Result[Terminal | None, GateStepFailed]:
    """Return the terminal Job status, or ``None`` when it is still running."""
    try:
        parsed = cast("_JobPayload", json.loads(payload))
    except json.JSONDecodeError as error:
        return Failure(unreadable(step=step, argv=argv, detail=f"unreadable job status: {error}"))
    status = parsed.get("status", {})
    conditions = cast("_Conditions", status.get("conditions", ()))
    for condition in conditions:
        if (
            condition.get("status") == _CONDITION_ASSERTED
            and condition.get("type") in _TERMINAL_CONDITION_TYPES
        ):
            return Success(Terminal(condition=condition["type"], status=status))
    return Success(None)
