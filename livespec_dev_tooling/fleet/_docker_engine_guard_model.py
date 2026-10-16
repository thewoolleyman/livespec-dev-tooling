"""The Docker engine install guard's value model: phases, operations and budgets.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" (this repository). Governing design:
`docs/docker-engine-guard-design.md`, revisions 5 to 8.

STDLIB ONLY, and that is a product constraint rather than a preference.
`docker_engine_guard.py` and the siblings beside it are copied onto a
factory host as `/usr/local/libexec/docker-engine-guard` and run there by
`systemd-run` transient units against the host's own interpreter — no
virtual environment, no vendored tree, no third-party package. So the
railway this repository otherwise rides (`dry-python/returns`) is not
importable where this code actually executes, and the module carries its
own refusal value (`GuardOutcome`, added as the operations land) instead:
an expected refusal is RETURNED, never raised, exactly as the Result rails
require — only the carrier differs. The package floor is Python 3.10, so
nothing here uses newer syntax.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, get_args

__all__: list[str] = [
    "DEFAULT_RUNTIME_ROOT",
    "DEFAULT_STATE_ROOT",
    "INSTALL_PHASES",
    "OPERATIONS",
    "PHASES",
    "ROLLBACK_PHASES",
    "Deadline",
    "Decision",
    "GuardOutcome",
    "GuardPaths",
    "Holder",
    "MarkerState",
    "Operation",
    "Phase",
    "Verdict",
    "operation_budget_seconds",
]

Phase = Literal[
    "reserved",
    "publishing",
    "published",
    "armed",
    "started",
    "observing",
    "observed",
    "committed",
    "confirmed",
    "rolling-back",
    "rolled-back",
    "rollback-partial",
]

Operation = Literal[
    "reserve",
    "publish",
    "arm",
    "start",
    "observe",
    "confirm",
    "rollback",
    "recover",
    "verify",
    "reconfigure",
]

# Derived from the `Literal`s rather than restated beside them: a second
# hand-written tuple is a second place the vocabulary can drift, and the
# dispatch table below indexes both by name.
PHASES: Final[tuple[Phase, ...]] = get_args(Phase)
OPERATIONS: Final[tuple[Operation, ...]] = get_args(Operation)

ROLLBACK_PHASES: Final[tuple[Phase, ...]] = ("rolling-back", "rolled-back", "rollback-partial")
INSTALL_PHASES: Final[tuple[Phase, ...]] = tuple(
    phase for phase in PHASES if phase not in ROLLBACK_PHASES
)

# `TimeoutStartSec` per operation (design H6). `observe` is the one entry
# that is not a flat number: its unit must outlive the whole observation
# window, so the window is added to the 300 s recorded here.
_BASE_BUDGET_SECONDS: Final[dict[Operation, int]] = {
    "reserve": 60,
    "publish": 1800,
    "arm": 60,
    "start": 180,
    "observe": 300,
    "confirm": 120,
    "rollback": 900,
    "recover": 1800,
    "verify": 120,
    "reconfigure": 120,
}


def operation_budget_seconds(*, operation: Operation, window_seconds: int) -> int:
    """The `TimeoutStartSec` the role gives this operation's transient unit.

    `window_seconds` is the observation window the preflight derives from
    the host's effective k3s resync periods; every operation but `observe`
    ignores it.
    """
    window = window_seconds if operation == "observe" else 0
    return _BASE_BUDGET_SECONDS[operation] + window


# How the commit marker reads for the run an operation was invoked on.
# `unreadable` sits with `other` rather than with `absent`, fail-closed: a
# marker that cannot be read is not evidence that no run committed.
MarkerState = Literal["absent", "self", "other", "unreadable"]

DEFAULT_STATE_ROOT: Final[Path] = Path("/var/lib/docker-engine-guard")
DEFAULT_RUNTIME_ROOT: Final[Path] = Path("/run/docker-engine-guard")


@dataclass(frozen=True, kw_only=True)
class GuardPaths:
    """Every durable and runtime location the guard reads or writes.

    The split is load-bearing rather than tidy. `runtime_root` is tmpfs, so
    the start permission and the lock vanish on a reboot while the commit
    marker and the run records under `state_root` do not — which is why a
    reboot before the commit point leaves no guarded unit able to start.
    """

    state_root: Path
    runtime_root: Path

    @property
    def marker(self) -> Path:
        """The commit marker. Its presence, not any phase, decides commitment."""
        return self.state_root / "confirmed"

    @property
    def reservation(self) -> Path:
        """The host's current reservation: one run id, or absent."""
        return self.state_root / "run"

    @property
    def lock(self) -> Path:
        """The one lock every operation takes. Created once, never replaced."""
        return self.runtime_root / "lock"

    @property
    def permission(self) -> Path:
        """The start permission the guarded units' start condition reads."""
        return self.runtime_root / "allow-start"

    def run_dir(self, *, run: str) -> Path:
        """One run's own directory: its phase, deadline, snapshot and inputs."""
        return self.state_root / "runs" / run

    def phase_path(self, *, run: str) -> Path:
        """The run's single phase record."""
        return self.run_dir(run=run) / "phase"

    def deadline_path(self, *, run: str) -> Path:
        """The run's boot-scoped monotonic deadline."""
        return self.run_dir(run=run) / "deadline.json"

    def snapshot_dir(self, *, run: str) -> Path:
        """The host snapshot `publish` takes once, before the first package step."""
        return self.run_dir(run=run) / "before"

    def inputs_dir(self, *, run: str) -> Path:
        """Where the controller uploads this run's inputs, and nowhere else."""
        return self.run_dir(run=run) / "inputs"


@dataclass(frozen=True, kw_only=True)
class Deadline:
    """A boot id and a CLOCK_MONOTONIC instant on that boot.

    A monotonic instant means nothing across a reboot, so the boot id is
    carried with it and a differing one counts as passed outright.
    """

    boot_id: str
    monotonic: float


# What an operation's row decided to do about this invocation. `finish`
# and `proceed` both reach the handler; they are distinguished because a
# committed run's handler does only the idempotent post-commit steps,
# with no challenge and no deadline.
Verdict = Literal["proceed", "finish", "noop", "refuse"]


@dataclass(frozen=True, kw_only=True)
class Decision:
    """What the dispatch table decided, and the reason it gives an operator."""

    verdict: Verdict
    reason: str


@dataclass(frozen=True, kw_only=True)
class Holder:
    """The run a refused `reserve` reports: its id, its phase and its deadline.

    All three, because an operator reading "refused" needs to know which
    run holds the host, how far it got, and when the dead-man will take
    it back — and the deadline is the only one of the three that says
    whether waiting is the right move.
    """

    run: str
    phase: Phase | None
    deadline: Deadline | None


@dataclass(frozen=True, kw_only=True)
class GuardOutcome:
    """One operation's result: what it decided, why, and what an operator must see."""

    operation: Operation
    run: str
    verdict: Verdict
    reason: str
    holder: Holder | None = None
    blocking_units: tuple[str, ...] = ()

    @property
    def exit_code(self) -> int:
        """Non-zero exactly when the operation refused, so its unit fails with it."""
        return 1 if self.verdict == "refuse" else 0
