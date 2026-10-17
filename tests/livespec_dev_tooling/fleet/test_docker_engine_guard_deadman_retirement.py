"""The Docker engine install guard's dead-man: what BOUNDS it, and what RETIRES it.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard" -- "Arm and the dead-man",
"Rollback" and "After the commit" (this repository). Governing design:
`docs/docker-engine-guard-design.md`, G5, H2 and H6.

Two defects in one lifecycle share this file because they are the same
concern read from its two ends. A dead-man that is never bounded holds
the guard lock forever when its rollback hangs; a dead-man that is never
retired keeps a timer in the air over a run that is already terminal,
and the role's own classify counts any non-inactive
`docker-engine-deadman-*` unit as a busy host -- so the host is refused
forever. Neither failure raises anything: the first presents as a lock
nobody holds any more, the second as a host that is simply never free.

Everything here runs against `FakeHost`, so the assertions are on the
seams the guard actually reaches: the `systemd_run` argv that arms the
dead-man, and the `stop_unit` calls that retire it.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

__all__: list[str] = []

_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_MODEL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_model.py")
_COMMIT_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_commit"
_COMMIT_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_commit.py")
_POSTCONDITIONS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_postconditions"
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"

# The observation window the design derives at preflight from the host's
# effective k3s resync periods. Only `observe`'s budget reads it; the
# dead-man's service budget is the flat rollback budget.
_WINDOW_SECONDS = 420


def _fake(*, root: Path) -> Any:
    """A `FakeHost` rooted at `root`, with the two guard state roots under it."""
    fake_module = importlib.import_module(_FAKE_MODULE)
    return fake_module.FakeHost(state_root=root / "var", runtime_root=root / "run")


def _paths(*, root: Path) -> Any:
    """`GuardPaths` for the two state roots `_fake` also uses."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def _env(*, root: Path, host: Any) -> Any:
    """A `GuardEnv` over those two roots, at the derived observation window."""
    state = importlib.import_module(_STATE_MODULE)
    return state.GuardEnv(paths=_paths(root=root), host=host, window_seconds=_WINDOW_SECONDS)


def _record_phase(*, root: Path, run: str, phase: str) -> None:
    """Put a reservation and a phase on disk the way the guard's records read."""
    state_root = root / "var"
    (state_root / "runs" / run).mkdir(parents=True, exist_ok=True)
    _ = (state_root / "run").write_text(run, encoding="utf-8")
    _ = (state_root / "runs" / run / "phase").write_text(phase, encoding="utf-8")


def _every_postcondition(*, holds: bool) -> dict[str, bool]:
    """The whole postcondition set, answered `holds` for every name.

    Keyed off the shipped `POSTCONDITIONS` tuple rather than a second
    hand-written list, because the names are the record's keys: a test
    spelling of them would answer under keys the guard never looks up
    and would read as a host that answered nothing.
    """
    postconditions = importlib.import_module(_POSTCONDITIONS_MODULE)
    return {name: holds for name in postconditions.POSTCONDITIONS}


def _stopped_units(*, fake: Any) -> tuple[str, ...]:
    """Every unit the host was asked to stop, in order."""
    return tuple(call.detail[0] for call in fake.calls_named(name="stop_unit"))


def _service_properties(*, argv: tuple[str, ...]) -> tuple[str, ...]:
    """Every `--property=` a `systemd-run` recipe passes, in its own order.

    The SERVICE properties alone: `--timer-property=` entries govern the
    timer half, which this comparison deliberately leaves out because
    the rollback unit has no timer at all.
    """
    return tuple(word for word in argv if word.startswith("--property="))


def test_the_dead_man_is_a_bounded_oneshot_carrying_the_rollbacks_stop_properties(
    tmp_path: Path,
) -> None:
    """Design H6: the dead-man's budget has to BOUND the rollback it runs.

    `systemd-run`'s default service type is `simple`, and for a `simple`
    service `TimeoutStartSec` bounds nothing once the process has
    started -- systemd considers such a unit started the moment it has
    forked. So the dead-man carried a 900-second budget that could not
    expire, and a rollback that hung while holding the guard lock (under
    SIGSTOP, FAULTS case C-03) was never killed and held the lock
    forever. `Type=oneshot` is what makes the budget bind: a oneshot
    unit is "starting" until its command EXITS.

    The three stop properties are the other half, and they are what
    makes the expiry reach anything. `TimeoutStopSec=30` bounds the
    stop, `KillMode=control-group` sends the signal to the rollback's
    whole cgroup rather than to its main process alone -- the driver
    spawns a child per phase -- and `SendSIGKILL=yes` is what ends a
    process that is stopped or ignoring SIGTERM.

    They are asserted as the rollback unit's OWN property set rather
    than as five strings, because that is the actual rule: the recipe
    `rollback_argv` builds for a triggered rollback already runs under
    exactly these bounds, the dead-man runs the same `rollback <run>`
    command, and the two drifting apart is how this defect arose.

    The timer half is asserted unchanged in the same breath. With
    `Type=oneshot` the service goes inactive when the rollback exits, so
    `--on-unit-inactive` still re-fires it 60 seconds later -- the
    repeat is what lets a rollback killed half way simply be repeated,
    and a fix that bounded the service by retiring the repeat would
    trade one defect for another.
    """
    assert _MODEL_PATH.is_file()
    guard = importlib.import_module(_GUARD_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    fake = _fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="published")

    outcome = guard.run_operation(operation="arm", run="run-a", env=_env(root=tmp_path, host=fake))

    assert outcome.exit_code == 0
    armed = fake.calls_named(name="systemd_run")[0].detail
    budget = model.operation_budget_seconds(operation="rollback", window_seconds=0)
    assert f"--property=TimeoutStartSec={budget}" in armed
    assert "--property=Type=oneshot" in armed
    assert "--property=TimeoutStopSec=30" in armed
    assert "--property=KillMode=control-group" in armed
    assert "--property=SendSIGKILL=yes" in armed
    assert _service_properties(argv=armed) == _service_properties(
        argv=model.rollback_argv(run="run-a")
    )
    assert "--on-unit-inactive=60" in armed
    assert "--timer-property=AccuracySec=1s" in armed
    assert "--collect" in armed
    assert armed[-2:] == ("rollback", "run-a")


def _verify(*, root: Path, postconditions: dict[str, bool]) -> tuple[Any, Any]:
    """Run `verify` through the whole guard with `postconditions` injected."""
    guard = importlib.import_module(_GUARD_MODULE)
    fake = _fake(root=root)
    fake.postconditions = postconditions
    return guard.run_operation(
        operation="verify", run="run-a", env=_env(root=root, host=fake)
    ), fake


def test_a_verify_that_promotes_a_partial_run_retires_that_runs_dead_man(
    tmp_path: Path,
) -> None:
    """Specification "After the commit", the `verify` sentence, read to its end.

    `verify` is how a `rollback-partial` run ever ends, and the
    promotion it writes is terminal: from `rolled-back` every later
    dead-man firing is decided `noop` by the dispatch table, so nothing
    will ever come back to that run again. The timer was nonetheless
    left in the air, re-firing every 60 seconds forever -- and the
    `docker_engine` role's classify counts ANY non-inactive
    `docker-engine-deadman-*` unit as a busy host, so a promoted run
    whose timer survived refuses the host to every later converge.
    Promoting without retiring the timer therefore buys nothing: it
    frees the reservation and leaves the host busy for the other
    reason.

    So the promotion and the retirement are one step, exactly as
    `confirm`'s post-commit steps already stop the same timer once a run
    is committed.

    A `verify` that REFUSES is the other half of the same rule and is
    asserted in the same test, because it is what keeps the retirement
    scoped to the promotion: a refusal means a rollback postcondition
    still fails, the run stays `rollback-partial`, and the dead-man is
    the only thing that will come back to repair it. Stopping its timer
    there would strand a host carrying a `docker0` or a residual Docker
    rule with nothing watching it. A refusing `verify` is a pure read,
    and it stays one -- it stops no unit at all.
    """
    assert _COMMIT_PATH.is_file()
    commit = importlib.import_module(_COMMIT_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    assert "deadman_timer_unit" in commit.__all__

    promoted = tmp_path / "promoted"
    _record_phase(root=promoted, run="run-a", phase="rollback-partial")
    outcome, host = _verify(root=promoted, postconditions=_every_postcondition(holds=True))

    assert outcome.verdict == "proceed"
    assert state.read_phase(paths=_paths(root=promoted), run="run-a") == "rolled-back"
    assert _stopped_units(fake=host) == (commit.deadman_timer_unit(run="run-a"),)

    refused = tmp_path / "still-partial"
    _record_phase(root=refused, run="run-a", phase="rollback-partial")
    failing = {**_every_postcondition(holds=True), "no docker0": False}
    outcome, host = _verify(root=refused, postconditions=failing)

    assert outcome.verdict == "refuse"
    assert state.read_phase(paths=_paths(root=refused), run="run-a") == "rollback-partial"
    assert _stopped_units(fake=host) == ()


def _deadman_firing(*, root: Path) -> tuple[Any, Any]:
    """One dead-man firing: the `rollback <run>` its timer's service runs."""
    guard = importlib.import_module(_GUARD_MODULE)
    fake = _fake(root=root)
    return (
        guard.run_operation(operation="rollback", run="run-a", env=_env(root=root, host=fake)),
        fake,
    )


def test_a_dead_man_firing_on_an_already_rolled_back_run_retires_its_own_timer(
    tmp_path: Path,
) -> None:
    """Specification "Dispatch table", the `rollback` row's `rolled-back` cell.

    The rollback driver retires its own timer when it writes a
    `rolled-back` outcome, so the ordinary path leaves nothing in the
    air. But the driver is only REACHED on a `proceed`: from
    `rolled-back` the table decides `noop`, and the guard returned that
    decision without touching the timer -- so every path that reached
    `rolled-back` other than through the driver's own final step left a
    dead-man firing every 60 seconds forever.

    Two real paths do exactly that. A `verify` killed between its
    promotion and its stop is one. A rollback killed between its
    outcome record and its stop is the other, and that one is not
    exotic at all: the outcome record is written durably and the stop
    is the step after it.

    The retirement belongs HERE rather than in another driver arm
    because a `noop` is the one answer that means "this run is terminal
    and nothing is left for a later firing to do". Deciding that and
    then leaving the thing that will fire again is the whole defect.
    """
    commit = importlib.import_module(_COMMIT_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    _record_phase(root=tmp_path, run="run-a", phase="rolled-back")

    outcome, host = _deadman_firing(root=tmp_path)

    assert outcome.verdict == "noop"
    assert outcome.exit_code == 0
    assert _stopped_units(fake=host) == (commit.deadman_timer_unit(run="run-a"),)
    assert state.read_phase(paths=_paths(root=tmp_path), run="run-a") == "rolled-back"
    assert host.calls_named(name="run_phase_child") == ()


def _publish_marker(*, root: Path, run: str) -> None:
    """Publish a commit marker naming `run`, the way `confirm` would."""
    state = importlib.import_module(_STATE_MODULE)
    state.write_durable(path=_paths(root=root).marker, data=json.dumps({"run": run, "digest": "d"}))


def test_a_dead_man_firing_on_a_run_the_commit_marker_names_retires_its_timer(
    tmp_path: Path,
) -> None:
    """Specification "Dispatch table", the `rollback` row's marker-names-this-run cell.

    A committed run is finished and must never be rolled back, which is
    why the table answers this firing `noop` rather than admitting it.
    `confirm`'s post-commit steps stop the same timer, LAST, for exactly
    that reason -- so on the ordinary path a committed run has no
    dead-man left.

    A `confirm` killed between the commit marker and that stop is the
    path this covers, and the window is real: the marker is written
    before the phase moves, by design R1, so a host can be committed
    with its dead-man still in the air and nothing but a later firing
    able to notice. Every such firing is decided `noop` and returned,
    which left the timer alive and the host classified busy forever.

    The retirement reads the DECISION rather than the phase, which is
    what makes one arm cover both terminal cells: the marker outranks
    the phase, so a committed run's phase may still read anything at
    all. Here it reads `committed` -- the phase a run holds between the
    commit rename and the post-commit steps, which is precisely where a
    killed `confirm` leaves it.
    """
    commit = importlib.import_module(_COMMIT_MODULE)
    state = importlib.import_module(_STATE_MODULE)
    _record_phase(root=tmp_path, run="run-a", phase="committed")
    _publish_marker(root=tmp_path, run="run-a")

    outcome, host = _deadman_firing(root=tmp_path)

    assert outcome.verdict == "noop"
    assert outcome.exit_code == 0
    assert _stopped_units(fake=host) == (commit.deadman_timer_unit(run="run-a"),)
    assert state.read_marker(paths=_paths(root=tmp_path), run="run-a") == "self"
    assert state.read_phase(paths=_paths(root=tmp_path), run="run-a") == "committed"
    assert host.calls_named(name="run_phase_child") == ()
