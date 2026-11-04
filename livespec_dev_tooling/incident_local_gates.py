"""Select and execute bounded local gates after trusted incident resolution."""

from __future__ import annotations

import math
import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

__all__: list[str] = [
    "GateReport",
    "GateResult",
    "GateSelection",
    "GateSpec",
    "ResolvedContext",
    "execute_plan",
    "route_resolved_gates",
    "select_gates",
]

MAX_GATE_SECONDS = 60.0

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
# Selection is deliberately separate from mode/receipt parsing. Only the shared
# trusted resolver may decide whether an entry point uses this execution plan.


@dataclass(frozen=True, kw_only=True)
class GateSpec:
    """One applicable check and its repository-owned timing classification."""

    name: str
    command: tuple[str, ...]
    classification: str


@dataclass(frozen=True, kw_only=True)
class GateSelection:
    """A check's execution or explicit deferral, before any subprocess starts."""

    gate: GateSpec
    selected: bool
    reason: str


@dataclass(frozen=True, kw_only=True)
class GateResult:
    """Measured result; deferred work never carries a passing return code."""

    name: str
    status: str
    reason: str
    returncode: int | None = None
    duration_seconds: float = 0.0
    output: str = ""


@dataclass(frozen=True, kw_only=True)
class GateReport:
    """Local-only evidence, explicitly unsuitable for normal aggregate caching."""

    results: tuple[GateResult, ...]
    exit_status: int
    evidence_kind: str = "expedited-local-partial"


class ResolvedContext(Protocol):
    """Structural view of the predecessor's canonical ExecutionContext.

    This interface accepts the resolver's result without parsing an environment,
    loading a receipt, or constructing a competing incident identity.
    """

    @property
    def mode(self) -> str:
        """The canonical resolver's mode."""
        ...

    @property
    def identity(self) -> object | None:
        """The canonical resolver's already-validated operation identity."""
        ...


def route_resolved_gates(
    *,
    context: ResolvedContext,
    gates: tuple[GateSpec, ...],
    cwd: Path,
    environment: Mapping[str, str] | None = None,
) -> GateReport | None:
    """Select before the caller does any ordinary precheck, cache or delegation.

    ``None`` selects the caller's unchanged normal path. Every other return is
    terminal for this entry point, including refusal. Callers must pass the
    shared resolver's context, never build one from a flag themselves.
    """
    if context.mode == "normal":
        return None
    if context.mode not in {"expedited-repair", "emergency-revert"} or context.identity is None:
        return GateReport(
            results=(
                GateResult(
                    name="incident-context",
                    status="failed",
                    reason="unresolved incident context",
                    returncode=78,
                ),
            ),
            exit_status=78,
        )
    if context.mode == "emergency-revert":
        return GateReport(
            results=tuple(
                GateResult(name=gate.name, status="deferred", reason="recorded emergency revert")
                for gate in gates
            ),
            exit_status=0,
        )
    return execute_plan(plan=select_gates(gates=gates), cwd=cwd, environment=environment)


def select_gates(*, gates: tuple[GateSpec, ...]) -> tuple[GateSelection, ...]:
    """Select declared fast gates; defer unknown classifications conservatively."""
    return tuple(
        GateSelection(
            gate=gate,
            selected=gate.classification == "fast",
            reason=(
                "declared fast gate"
                if gate.classification == "fast"
                else "known slow gate"
                if gate.classification == "slow"
                else "gate has no fast timing classification"
            ),
        )
        for gate in gates
    )


def _kill_group(*, pid: int) -> None:
    """Reap the owned session's descendants, including children ignoring TERM."""
    with suppress(ProcessLookupError):
        os.killpg(pid, signal.SIGKILL)


def _run_gate(
    *, gate: GateSpec, cwd: Path, deadline_seconds: float, environment: Mapping[str, str]
) -> GateResult:
    started = time.monotonic()
    if not gate.command:
        return GateResult(
            name=gate.name, status="failed", reason="empty gate command", returncode=127
        )
    with tempfile.TemporaryFile() as output:
        try:
            process = subprocess.Popen(  # noqa: S603 — repository-owned argv; never a shell string.
                gate.command,
                cwd=cwd,
                env=dict(environment),
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except OSError as error:
            return GateResult(name=gate.name, status="failed", reason=str(error), returncode=127)
        try:
            code = process.wait(timeout=deadline_seconds)
        except subprocess.TimeoutExpired:
            code = None
        finally:
            _kill_group(pid=process.pid)
            _ = process.wait()
        _ = output.seek(0)
        captured = output.read().decode("utf-8", errors="replace")
    return GateResult(
        name=gate.name,
        status="deferred-timeout" if code is None else "passed" if code == 0 else "failed",
        reason="local gate deadline reached" if code is None else "gate completed",
        returncode=code,
        duration_seconds=time.monotonic() - started,
        output=captured,
    )


def execute_plan(
    *,
    plan: tuple[GateSelection, ...],
    cwd: Path,
    deadline_seconds: float = MAX_GATE_SECONDS,
    environment: Mapping[str, str] | None = None,
) -> GateReport:
    """Run selected checks sequentially with a hard per-process-group deadline.

    No cluster probe, aggregate, cache lookup or normal evidence writer runs here.
    The caller records the report against its already-resolved incident context.
    """
    if not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= MAX_GATE_SECONDS:
        message = "gate deadline must be positive and at most sixty seconds"
        raise ValueError(message)
    child_env = dict(os.environ if environment is None else environment)
    results = tuple(
        _run_gate(
            gate=entry.gate, cwd=cwd, deadline_seconds=deadline_seconds, environment=child_env
        )
        if entry.selected
        else GateResult(name=entry.gate.name, status="deferred", reason=entry.reason)
        for entry in plan
    )
    status = next((result.returncode for result in results if result.returncode), 0)
    return GateReport(results=results, exit_status=status if status >= 0 else 128 - status)
