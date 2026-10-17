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
    "DEADLINE_MARGIN_SECONDS",
    "DEFAULT_RUNTIME_ROOT",
    "DEFAULT_STATE_ROOT",
    "DEFAULT_WINDOW_SECONDS",
    "GUARDED_UNITS",
    "GUARD_EXECUTABLE",
    "INSTALL_PHASES",
    "OPERATIONS",
    "PHASES",
    "ROLLBACK_PHASES",
    "START_ORDER",
    "UNIT_WAIT_SECONDS",
    "Deadline",
    "Decision",
    "GuardOutcome",
    "GuardPaths",
    "Holder",
    "MarkerState",
    "Operation",
    "Phase",
    "Verdict",
    "deadline_seconds",
    "deadman_argv",
    "operation_budget_seconds",
    "rollback_argv",
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


# The three units the guard drop-ins condition, in sorted order. Every
# kill, stop and disable the guard issues names one of exactly these, so
# k3s-agent.service and its own containerd are never reachable.
GUARDED_UNITS: Final[tuple[str, ...]] = (
    "containerd.service",
    "docker.service",
    "docker.socket",
)

# `start` brings these two up, in this order: docker needs containerd's
# socket, so the reverse order is a docker.service that fails its start.
# docker.socket is deliberately absent — the guard never starts it.
START_ORDER: Final[tuple[str, ...]] = ("containerd.service", "docker.service")

# The bounded wait on each guarded unit start. Two of them plus the lock
# wait fit inside `start`'s own 180-second budget, so a daemon that never
# becomes ready ends as a refusal rather than as a transient unit
# SIGKILLed with no verdict at all.
UNIT_WAIT_SECONDS: Final[int] = 60

# Where the role installs this executable on the guarded host, and so the
# command every transient unit the guard arms runs.
GUARD_EXECUTABLE: Final[Path] = Path("/usr/local/libexec/docker-engine-guard")

# The observation window at the resync periods measured on 2026-10-15. The
# role overrides it with the window its preflight derives from the host's
# own effective k3s intervals; this is the value a guard invoked without
# one assumes, and it is deliberately the LONGER of the measured defaults.
DEFAULT_WINDOW_SECONDS: Final[int] = 420

# Slack between the work the deadline has to cover and the deadline
# itself, so an operation that runs to the end of its own budget does not
# lose the run to the dead-man by seconds.
DEADLINE_MARGIN_SECONDS: Final[int] = 300

# How often the dead-man re-fires after each rollback it runs, until a
# rollback outcome or a confirmation stops it.
DEADMAN_REPEAT_SECONDS: Final[int] = 60


def deadline_seconds(*, window_seconds: int) -> int:
    """N: how far ahead of arming the run's deadline is recorded.

    Derived from the same budget table the role passes to each
    operation's unit rather than written down beside it, so a budget
    that moves moves the deadline with it instead of leaving a dead-man
    that fires in the middle of an observation window.
    """
    covered = ("start", "observe", "confirm")
    return (
        sum(
            operation_budget_seconds(operation=operation, window_seconds=window_seconds)
            for operation in covered
        )
        + DEADLINE_MARGIN_SECONDS
    )


def _rollback_service_properties() -> tuple[str, ...]:
    """The `--property=` set every unit running `rollback <run>` is bounded by.

    ONE set, shared by the two recipes below, because a dead-man and a
    triggered rollback run the SAME command and a rollback that is
    bounded on one path and not the other is the defect this exists to
    rule out.

    `Type=oneshot` is the load-bearing entry and the one that was
    missing from the dead-man. `systemd-run`'s default service type is
    `simple`, and systemd considers a `simple` unit started the moment
    it has forked — so `TimeoutStartSec` bounds nothing at all once the
    rollback is running, and a rollback that hangs while holding the
    guard lock holds it forever. A `oneshot` unit is "starting" until
    its command EXITS, which is what makes the budget bind.

    The budget itself is the WHOLE rollback budget, so the primary
    rollback is never killed before its final postcondition check. The
    three stop properties are what make the expiry reach anything:
    `TimeoutStopSec` bounds the stop, `KillMode=control-group` signals
    the rollback's whole cgroup rather than its main process alone (the
    driver spawns a child per phase), and `SendSIGKILL` ends a process
    that is stopped or ignoring SIGTERM.
    """
    rollback_budget = operation_budget_seconds(operation="rollback", window_seconds=0)
    return (
        "--property=Type=oneshot",
        f"--property=TimeoutStartSec={rollback_budget}",
        "--property=TimeoutStopSec=30",
        "--property=KillMode=control-group",
        "--property=SendSIGKILL=yes",
    )


def deadman_argv(*, run: str, on_active_seconds: int) -> tuple[str, ...]:
    """The `systemd-run` that arms this run's dead-man.

    `--on-active` is the interval REMAINING to the already-recorded
    deadline, not N, so a delayed arming still fires at the recorded
    instant. `--on-unit-inactive` makes it re-fire after each rollback
    it runs, which is what lets a rollback killed half way simply be
    repeated a minute later — and it keeps working under
    `Type=oneshot`, because such a service goes inactive exactly when
    the rollback exits.

    Its service properties are the rollback unit's, whole, for the
    reason `_rollback_service_properties` records: the two run the same
    command, so the dead-man carrying a weaker bound than the triggered
    path is a dead-man whose own budget cannot kill it.
    """
    return (
        "systemd-run",
        "--collect",
        f"--unit=docker-engine-deadman-{run}",
        f"--on-active={on_active_seconds}",
        f"--on-unit-inactive={DEADMAN_REPEAT_SECONDS}",
        "--timer-property=AccuracySec=1s",
        *_rollback_service_properties(),
        str(GUARD_EXECUTABLE),
        "rollback",
        run,
    )


def rollback_argv(*, run: str) -> tuple[str, ...]:
    """The `systemd-run` that starts a rollback as its own transient unit.

    Used where a rollback must be TRIGGERED by something already holding
    the lock, which cannot call the rollback entry in-process without
    deadlocking on that lock. `--no-block` so the trigger does not wait
    on it, and the unit name carries the run so a second trigger while
    one is already running is refused by the service manager rather than
    starting a second driver.
    """
    return (
        "systemd-run",
        "--collect",
        "--no-block",
        f"--unit=docker-engine-guard-rollback-{run}",
        *_rollback_service_properties(),
        str(GUARD_EXECUTABLE),
        "rollback",
        run,
    )


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

    def snapshot_taken_path(self, *, run: str) -> Path:
        """The marker written inside the snapshot once the host snapshot COMPLETED.

        Written only after the host action returns, so a resumed
        `publish` can tell "already snapshotted" from "interrupted part
        way through snapshotting" and retake the second. Its ABSENCE
        carries a second fact a rollback reads: `publish` is also what
        installs the first package, so a run with no snapshot has had
        nothing started behind it at all.
        """
        return self.snapshot_dir(run=run) / "taken"

    def inputs_dir(self, *, run: str) -> Path:
        """Where the controller uploads this run's inputs, and nowhere else."""
        return self.run_dir(run=run) / "inputs"

    def rollback_dir(self, *, run: str) -> Path:
        """This run's rollback bookkeeping, beside its other records.

        The per-phase attempt counts, success records and findings the
        driver writes, and the outcome record an operator and a later
        `verify` read.
        """
        return self.run_dir(run=run) / "rollback"


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


def _deadline_text(*, deadline: Deadline | None) -> str:
    """A deadline rendered for an operator, or the fact that none was recorded."""
    if deadline is None:
        return "none recorded"
    return f"{deadline.boot_id}@{deadline.monotonic:.0f}"


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

    def report_lines(self) -> tuple[str, ...]:
        """What the operator reads: the verdict, the holder, and what blocked it.

        A refusal that does not name the holding run leaves an operator
        with no next step, and the holder's DEADLINE is the field that
        says whether waiting is one — a deadline already past means the
        dead-man is about to take the host back by itself.
        """
        lines = [f"{self.operation} {self.verdict}: {self.reason}"]
        if self.holder is not None:
            lines.append(
                f"holder: run={self.holder.run} phase={self.holder.phase} "
                f"deadline={_deadline_text(deadline=self.holder.deadline)}"
            )
        if self.blocking_units:
            lines.append(f"not quiescent: {', '.join(self.blocking_units)}")
        return tuple(lines)
