"""Consumer-tier: the seven `SPECIFICATION/scenarios.md` Docker engine install guard scenarios.

The scenarios, in the order `scenarios.md` states them and the order the arms below
follow:

  - a second controller cannot reserve the Docker engine install guard while a run is
    unfinished
  - the Docker engine install guard refuses to start without a live dead-man
  - a Docker engine install guard deadline recorded on an earlier boot counts as passed
  - a Docker engine install guard confirm that arrives after the deadline loses to the
    rollback
  - a Docker engine install guard run named by the commit marker is finished, never
    rolled back
  - a Docker engine install guard rollback phase that keeps killing the driver does not
    stop the later phases
  - the Docker engine install guard's recover resumes an interrupted publish and rolls
    back any other uncommitted run

Each exercises the COMBINED behaviour of the six guard children, which is why it is
answered here rather than in any one child's own file: the first needs a run that
`reserve`, `publish`, `arm`, `start` and `observe` carried as far as `observing`; the
fourth and fifth need an evidence record and a challenge the real observer wrote and a
commit marker the real `confirm` published; the seventh needs a publish whose snapshot
was genuinely taken before its package step.

HOW THESE DRIVE THE GUARD, AND WHY IT IS THE COMMAND LINE. Every arm invokes
`_docker_engine_guard_cli.parse_request` and `docker_engine_guard.run_request` — the
whole surface the role's transient `systemd-run` units reach — so what is asserted is
the exit code an operator's unit fails with, the REPORT that operator reads, the durable
records the next invocation dispatches on, and the host actions the guard took. Nothing
here reads a `GuardOutcome` object: a scenario is a claim about observable behaviour, and
an operator on a machine reachable only over Tailscale observes exactly those four.

THE HOST IS `FakeHost`, AND THE TWO STATE ROOTS AND THE CLOCK ARE INJECTED. The guard
touches the world only through the `HostOps` protocol, so the whole lifecycle runs
in-process with no real host action, no subprocess and no clock. `FakeHost` records every
seam call stamped with the phase in force when it arrived, which is what lets an ordering
between a durable record and a host action be asserted at all.

...AND A FEW SEAMS ARE REFLECTED BACK INTO IT, because a scenario that spans operations
needs the host to REMEMBER. `_host` makes `start_unit` / `stop_unit` / `enable_units`
move the unit states the NEXT operation reads, so the post-commit validation sees the
units `confirm` actually enabled and started rather than a state a test declared;
`_arming_host` additionally makes `systemd-run --unit=docker-engine-deadman-<run>` put
that timer in the air, so `start`'s dead-man check reads a timer `arm` really armed.
Scenario two deliberately uses the host WITHOUT that reflection: a `systemd-run` that was
issued and a timer that never came up is exactly the state it is about.

HOW A KILLED PROCESS IS MODELLED. Three scenarios turn on a guard invocation that died
part way — an observer SIGKILLed mid-window, a publish whose package step was
interrupted, a rollback driver its own phase child takes down. Each is a `RuntimeError`
raised out of the seam the kill landed on: the guard has no handler for it, so the
invocation ends exactly where the kill landed, having written whatever it had already
written and nothing after. That is the state the next invocation finds, and the records
it finds are the whole subject of the scenario.

CONTROL ARMS. The two `start` refusals are each paired with the same invocation over a
host differing in ONE fact — the dead-man timer's activity, the boot id — so a refusal
that fired for some other reason cannot pass as the scenario's. The post-deadline
`confirm` reads back that every OTHER clause of the commit rule was satisfied at the
moment it refused (the evidence records a pass, and the challenge is younger than its
maximum age), so the deadline is proven to be the sole cause. The committed-run arm
deletes the challenge before its `confirm`, which is what proves the committed path
consults none.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
_CLI_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_cli"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"
_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_RECORDS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_records"
_ROLLBACK_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_rollback"

_GUARD_PATH = Path("livespec_dev_tooling/fleet/docker_engine_guard.py")

# The one run id every arm drives, and the second controller's in scenario one.
_RUN = "run-a"
_OTHER_RUN = "run-b"

# The transient timer `arm` puts in the air for `_RUN`, under the two spellings
# the guard uses: the `systemd-run --unit=` value, and the `.timer` unit a
# finished driver or a finished `confirm` stops.
_DEADMAN_UNIT = f"docker-engine-deadman-{_RUN}"
_DEADMAN_TIMER = f"{_DEADMAN_UNIT}.timer"

# What the observer's sample has to carry for the window to go on. Read
# fail-closed by the observer, so anything else ends the window.
_PASSING_SAMPLE: dict[str, object] = {"passed": True}

# Bytes written over the first snapshot an interrupted publish took, so a
# resume that RETOOK it rather than keeping it is visible in the file itself
# and not merely absent from the call record.
_FIRST_SNAPSHOT = "# the first snapshot\n"


def _module(*, name: str) -> Any:
    """One of the guard's modules, imported the way the guard imports its siblings."""
    return importlib.import_module(name)


def _paths(*, root: Path) -> Any:
    """`GuardPaths` over the two state roots every arm drives the guard against.

    `var` stands in for `/var/lib/docker-engine-guard` and `run` for the tmpfs
    `/run/docker-engine-guard`; the split is what makes the commit marker and the
    run records outlive a reboot while the start permission and the lock do not.
    """
    model = _module(name=_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def _active_states_of(*, fake: Any, unit: str) -> dict[str, str]:
    """The map holding `unit`'s active state: the guarded units' own, or the guard's."""
    return (
        fake.guarded_unit_states
        if unit in _module(name=_MODEL_MODULE).GUARDED_UNITS
        else fake.unit_states
    )


def _service_manager(*, fake: Any) -> None:
    """Let the unit actions the guard takes move the unit states it later reads.

    Without this the host would forget: the post-commit validation reads the
    guarded units' ACTIVE and ENABLED states back through the same two seams
    `confirm` just acted on, so a host that did not remember would have to be
    told what it is running by the test rather than by the guard.

    The three seams reflected are the three the guard itself drives in-process.
    A rollback phase's own unit actions are NOT among them: each phase body runs
    in a child process the driver spawns, and `run_phase_child` answers whether
    that child completed rather than running the body here.

    A started or stopped unit lands in whichever map the real host would answer
    for it -- the guarded units' own, or the guard's. The guard both starts the
    three guarded units and stops its dead-man timer, and a host that filed
    either under the other's map would be answering a read the real one cannot.
    """
    start_unit = fake.start_unit
    stop_unit = fake.stop_unit
    enable_units = fake.enable_units

    def starting(*, unit: str, timeout_seconds: int) -> None:
        start_unit(unit=unit, timeout_seconds=timeout_seconds)
        _active_states_of(fake=fake, unit=unit)[unit] = "active"

    def stopping(*, unit: str, timeout_seconds: int) -> None:
        stop_unit(unit=unit, timeout_seconds=timeout_seconds)
        _active_states_of(fake=fake, unit=unit)[unit] = "inactive"

    def enabling(*, units: Sequence[str]) -> None:
        enable_units(units=units)
        fake.unit_file_states.update({unit: "enabled" for unit in units})

    fake.start_unit = starting
    fake.stop_unit = stopping
    fake.enable_units = enabling


def _host(*, root: Path) -> Any:
    """A `FakeHost` whose service manager remembers, and whose dead-man never comes up.

    The second scenario's whole subject: `arm` issues its `systemd-run` and the
    timer does not become active, so `start` has nothing watching the host.
    """
    fake = _module(name=_FAKE_MODULE).FakeHost(state_root=root / "var", runtime_root=root / "run")
    fake.sample_result = dict(_PASSING_SAMPLE)
    _service_manager(fake=fake)
    return fake


def _arming_host(*, root: Path) -> Any:
    """`_host`, plus a `systemd-run` that really puts a dead-man timer in the air.

    `arm` builds the `--unit=docker-engine-deadman-<run>` argv and hands it to
    the host; reflecting it back is what lets `start`'s dead-man check read a
    timer the guard itself armed rather than one a test declared live.
    """
    fake = _host(root=root)
    systemd_run = fake.systemd_run

    def arming(*, argv: Sequence[str]) -> None:
        systemd_run(argv=argv)
        for word in argv:
            if word.startswith("--unit=docker-engine-deadman-"):
                fake.deadman_units.add(word.removeprefix("--unit="))
                fake.active_deadman_units.add(word.removeprefix("--unit="))

    fake.systemd_run = arming
    return fake


def _invoke(*, root: Path, host: Any, argv: Sequence[str]) -> int:
    """Run ONE guard invocation exactly as the role's transient unit runs it.

    The state roots are forwarded because an acceptance host is driven somewhere
    other than `/var/lib` and `/run`; everything else about the command line is
    the operator's own.
    """
    assert _GUARD_PATH.is_file()
    guard = _module(name=_GUARD_MODULE)
    cli = _module(name=_CLI_MODULE)
    request = cli.parse_request(
        argv=[
            *argv,
            "--state-root",
            str(root / "var"),
            "--runtime-root",
            str(root / "run"),
        ]
    )
    return guard.run_request(request=request, host=host)


def _phase_of(*, root: Path, run: str) -> Any:
    """The run's recorded phase, read the way every guard operation reads it."""
    state = _module(name=_STATE_MODULE)
    return state.read_phase(paths=_paths(root=root), run=run)


def _deadline_of(*, root: Path, run: str) -> Any:
    """The run's recorded deadline: a boot id and a CLOCK_MONOTONIC instant on it."""
    state = _module(name=_STATE_MODULE)
    return state.read_deadline(paths=_paths(root=root), run=run)


def _reported(*, caplog: pytest.LogCaptureFixture) -> str:
    """Everything the invocation reported where an operator reads it."""
    return "\n".join(record.getMessage() for record in caplog.records)


def _drive_to_started(*, root: Path, host: Any) -> None:
    """Take the run from an unused host to `started`, through the guard's own operations.

    No step is simulated: the reservation, the snapshot, the inert install, the
    recorded deadline, the armed dead-man and the start permission are all the
    guard's own work, which is what makes the records the later arms read the
    records a real run leaves behind.
    """
    for operation in ("reserve", "publish", "arm", "start"):
        assert _invoke(root=root, host=host, argv=[operation, _RUN]) == 0, operation
    assert _phase_of(root=root, run=_RUN) == "started"


def _drive_to_observed(*, root: Path, host: Any) -> None:
    """`_drive_to_started`, then one whole observation window that passes."""
    _drive_to_started(root=root, host=host)
    assert _invoke(root=root, host=host, argv=["observe", _RUN]) == 0
    assert _phase_of(root=root, run=_RUN) == "observed"


def _answer_the_challenge(*, root: Path) -> Any:
    """Upload the controller's answer to the outstanding challenge, and hand it back.

    The answer goes into the run's own `inputs/` directory because that is the
    one place a controller may write; the guard never has a record written into
    place for it.
    """
    records = _module(name=_RECORDS_MODULE)
    paths = _paths(root=root)
    challenge = records.read_challenge(paths=paths)
    assert challenge is not None
    answer = paths.inputs_dir(run=_RUN) / "challenge-answer"
    _ = answer.write_text(challenge.nonce, encoding="utf-8")
    return challenge


def _every_postcondition_holds(*, fake: Any) -> None:
    """Make the host answer the whole rollback postcondition set as holding.

    Read from the driver's own specified set rather than restated, so a set that
    grows a postcondition reaches these arms instead of leaving them green over a
    narrower read than the final check performs.
    """
    rollback = _module(name=_ROLLBACK_MODULE)
    fake.postconditions = {name: True for name in rollback.POSTCONDITIONS}


def _kill_at(*, fake: Any, seam: str, after: int) -> None:
    """Make the `seam` call numbered `after` take the whole invocation down with it.

    A `RuntimeError` out of a host seam is how a guard process KILLED mid-step is
    modelled: nothing above it handles the exception, so the invocation ends
    where the kill landed, having written whatever it had already written and no
    record after it. The seam is called first and kills second, which is the real
    sequence — the step WAS entered, and for a rollback phase it is the ENTRY the
    attempt budget counts.
    """
    called = getattr(fake, seam)
    seen: list[int] = []

    def killing(**kwargs: Any) -> Any:
        completed = called(**kwargs)
        seen.append(len(seen) + 1)
        if len(seen) == after:
            raise RuntimeError(f"the {seam} call killed the guard")
        return completed

    setattr(fake, seam, killing)


def _kill_the_driver_at(*, fake: Any, phase: str) -> None:
    """Make the child the rollback driver spawns for `phase` take the driver down.

    Named by PHASE rather than by call number, because which call a phase's
    child is varies across firings: a phase holding a recorded success is
    skipped, so the second firing's second spawn is already a later phase. The
    scenario is about one phase killing the driver EVERY TIME IT IS ENTERED, and
    the phase name is the only thing that says so.
    """
    spawn = fake.run_phase_child

    def killing_spawn(*, argv: Sequence[str]) -> bool:
        completed = spawn(argv=argv)
        if argv[-1] == phase:
            raise RuntimeError(f"the {phase} child killed the rollback driver")
        return completed

    fake.run_phase_child = killing_spawn


def _interrupt_a_publish(*, root: Path) -> Path:
    """Leave the run resting in `publishing` with its snapshot taken, and mark its bytes.

    The interruption is the package step being killed, which is what a publish
    interrupted on a real host looks like: the phase reached `publishing` and the
    snapshot was taken and recorded as COMPLETE before the first package moved,
    so a recovery has a baseline to compare against and the run is inert behind
    it. The snapshot's bytes are then marked, so a resume that RETOOK it would
    be visible rather than merely uncounted.
    """
    fake = _host(root=root)
    _kill_at(fake=fake, seam="install_packages", after=1)
    assert _invoke(root=root, host=fake, argv=["reserve", _RUN]) == 0
    with pytest.raises(RuntimeError):
        _ = _invoke(root=root, host=fake, argv=["publish", _RUN])
    paths = _paths(root=root)
    snapshot = paths.snapshot_dir(run=_RUN) / "iptables-save"
    assert _phase_of(root=root, run=_RUN) == "publishing"
    assert snapshot.is_file()
    assert not paths.marker.exists()
    _ = snapshot.write_text(_FIRST_SNAPSHOT, encoding="utf-8")
    return snapshot


def test_a_second_controller_cannot_reserve_while_a_run_is_unfinished(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: a second controller cannot reserve the guard while a run is unfinished.

    Run A is carried to `observing` by the guard's own operations and then its
    observer is SIGKILLed mid-window, which is how a run comes to REST in that
    phase: the window never finished, so nothing moved it on. A second
    controller's `reserve` then has to be actionable rather than merely refused —
    the run id says which controller owns the host, the phase says how far it
    got, and the deadline is the only one of the three that says whether waiting
    is the right move or whether the dead-man has already been and gone.

    And it must change nothing. A controller that merely lost the race has to
    leave run A's phase, its deadline and its dead-man exactly as it found them;
    a reserve that nudged any of the three would take time away from a run that
    still has it.
    """
    root = tmp_path
    fake = _arming_host(root=root)
    _drive_to_started(root=root, host=fake)
    _kill_at(fake=fake, seam="sample", after=3)
    with pytest.raises(RuntimeError):
        _ = _invoke(root=root, host=fake, argv=["observe", _RUN])
    assert _phase_of(root=root, run=_RUN) == "observing"
    held = _deadline_of(root=root, run=_RUN)
    assert held is not None
    armings = len(fake.calls_named(name="systemd_run"))

    with caplog.at_level("INFO"):
        code = _invoke(root=root, host=fake, argv=["reserve", _OTHER_RUN])

    assert code == 1
    report = _reported(caplog=caplog)
    assert _RUN in report
    assert "observing" in report
    assert f"{held.boot_id}@{held.monotonic:.0f}" in report
    # Unchanged: the phase, the deadline, the dead-man — and the reservation,
    # which is what makes the host still run A's.
    assert _phase_of(root=root, run=_RUN) == "observing"
    assert _deadline_of(root=root, run=_RUN) == held
    assert fake.deadman_timer_active(run=_RUN) is True
    assert len(fake.calls_named(name="systemd_run")) == armings
    state = _module(name=_STATE_MODULE)
    assert state.read_reservation(paths=_paths(root=root)) == _RUN
    assert _phase_of(root=root, run=_OTHER_RUN) is None


def test_the_guard_refuses_to_start_without_a_live_dead_man(tmp_path: Path) -> None:
    """Scenario: the guard refuses to start without a live dead-man.

    The dead-man is the only thing that takes the host back if the controller
    dies, so granting the start permission without one would leave a Docker
    daemon nothing is watching on a machine nobody can power-cycle. The run is
    `armed` and its deadline has not passed — `arm` issued its `systemd-run` and
    the timer simply never came up, which is the one fact that must stop it.

    The CONTROL is the same invocation over the same records once that timer is
    active: it grants, so the refusal above cannot have fired for any other
    reason.
    """
    root = tmp_path
    fake = _host(root=root)
    for operation in ("reserve", "publish", "arm"):
        assert _invoke(root=root, host=fake, argv=[operation, _RUN]) == 0, operation
    assert _phase_of(root=root, run=_RUN) == "armed"
    assert fake.deadman_timer_active(run=_RUN) is False
    held = _deadline_of(root=root, run=_RUN)
    assert held is not None
    assert held.monotonic > fake.monotonic()

    code = _invoke(root=root, host=fake, argv=["start", _RUN])

    assert code == 1
    assert fake.calls_named(name="grant_start_permission") == ()
    assert fake.calls_named(name="start_unit") == ()
    assert not _paths(root=root).permission.exists()
    assert _phase_of(root=root, run=_RUN) == "armed"

    fake.active_deadman_units.add(_DEADMAN_UNIT)
    assert _invoke(root=root, host=fake, argv=["start", _RUN]) == 0
    assert len(fake.calls_named(name="grant_start_permission")) == 1


def test_a_deadline_recorded_on_an_earlier_boot_counts_as_passed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: a guard deadline recorded under an earlier boot id counts as passed.

    A CLOCK_MONOTONIC instant means nothing across a reboot, so the boot id is
    recorded with it and a differing one counts as passed outright — whatever the
    instant says. Here the instant is still far away and the dead-man is live, so
    the boot id is the only thing wrong, and `start` must refuse BECAUSE the
    deadline has passed and grant nothing.

    The dead-man is deliberately left live across the boot change. A real reboot
    would also take the transient timer with it, and `start` would then have two
    reasons to refuse; holding it live isolates the boot id as the sole cause,
    which is what the scenario asserts.

    The CONTROL restores the boot id and nothing else: the same records, the same
    clock and the same host then grant the permission.
    """
    root = tmp_path
    fake = _arming_host(root=root)
    for operation in ("reserve", "publish", "arm"):
        assert _invoke(root=root, host=fake, argv=[operation, _RUN]) == 0, operation
    recorded = _deadline_of(root=root, run=_RUN)
    assert recorded is not None
    assert recorded.boot_id == "boot-a"
    # The host rebooted: a fresh boot id, and a monotonic clock that restarted
    # far below the instant the deadline names.
    fake.boot = "boot-b"
    fake.clock = 1.0
    assert recorded.monotonic > fake.monotonic()
    assert fake.deadman_timer_active(run=_RUN) is True

    with caplog.at_level("INFO"):
        code = _invoke(root=root, host=fake, argv=["start", _RUN])

    assert code == 1
    assert "deadline has passed" in _reported(caplog=caplog)
    assert fake.calls_named(name="grant_start_permission") == ()
    assert fake.calls_named(name="start_unit") == ()
    assert not _paths(root=root).permission.exists()
    assert _phase_of(root=root, run=_RUN) == "armed"

    fake.boot = "boot-a"
    assert _invoke(root=root, host=fake, argv=["start", _RUN]) == 0
    assert len(fake.calls_named(name="grant_start_permission")) == 1


def test_a_confirm_that_arrives_after_the_deadline_loses_to_the_rollback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Scenario: a guard confirm that arrives after the deadline loses to the rollback.

    The run is `observed` with the evidence record and the challenge the real
    observer wrote, and the controller has answered with that challenge's nonce.
    The one thing against it is the clock: the instant its deadline names has
    arrived, so the dead-man is owed this host and the commit must not be allowed
    to race it. `confirm` refuses, the commit marker is never written, and the
    `rollback` that follows takes the run back.

    EVERY OTHER CLAUSE OF THE COMMIT RULE IS SATISFIED, and that is asserted
    rather than assumed: the evidence records a passing window and the challenge
    is younger than its maximum age at the moment of the refusal. So the deadline
    is the sole cause, and a refusal that had come from a stale challenge or a
    failed window could not pass as this scenario's.
    """
    root = tmp_path
    fake = _arming_host(root=root)
    _every_postcondition_holds(fake=fake)
    _drive_to_observed(root=root, host=fake)
    challenge = _answer_the_challenge(root=root)
    records = _module(name=_RECORDS_MODULE)
    state = _module(name=_STATE_MODULE)
    model = _module(name=_MODEL_MODULE)
    paths = _paths(root=root)
    assert records.evidence_passed(paths=paths, run=_RUN) is True
    assert fake.monotonic() - challenge.issued_monotonic < records.CHALLENGE_MAX_AGE_SECONDS
    # The dead-man's instant has arrived. Recorded rather than waited out,
    # because the deadline is a CLOCK_MONOTONIC instant on this boot and the
    # clock is the one thing a test may inject.
    state.write_deadline(
        paths=paths,
        run=_RUN,
        deadline=model.Deadline(boot_id=fake.boot_id(), monotonic=fake.monotonic()),
    )

    with caplog.at_level("INFO"):
        code = _invoke(root=root, host=fake, argv=["confirm", _RUN])

    assert code == 1
    assert "deadline has passed" in _reported(caplog=caplog)
    assert not paths.marker.exists()
    assert _phase_of(root=root, run=_RUN) == "observed"
    assert records.consumed_nonces(paths=paths, run=_RUN) == ()

    rolling = _arming_host(root=root)
    _every_postcondition_holds(fake=rolling)

    assert _invoke(root=root, host=rolling, argv=["rollback", _RUN]) == 0

    assert _phase_of(root=root, run=_RUN) == "rolled-back"
    assert not paths.marker.exists()
    assert rolling.calls_named(name="revoke_start_permission") != ()


def test_a_run_named_by_the_commit_marker_is_finished_never_rolled_back(
    tmp_path: Path,
) -> None:
    """Scenario: a guard run the commit marker names is finished, never rolled back.

    The state is the one a crash past the commit point leaves: `confirm` wrote
    the marker, recorded `committed`, revoked the start permission and was then
    killed as it enabled the units. The marker — never the phase — is what
    decides commitment, so the run is committed whatever its phase reads.

    `rollback` therefore exits 0 having rolled NOTHING back. Not "having rolled
    back safely": a committed host's guarded units already honour the marker
    through their own start condition, so a rollback that acted would undo a
    commitment the host is already keeping. The assertion is on every acting
    seam, because exiting 0 is the easy half.

    The ONE thing the no-op does is RETIRE this run's dead-man timer, and that
    is the opposite of acting on the commitment: the kill above landed between
    the commit marker and the stop `confirm` performs last, so a timer is still
    in the air over a run that must never be rolled back — and the role's
    classify counts any non-inactive `docker-engine-deadman-*` unit as a busy
    host, which would refuse this host for the rest of the boot. Nothing else
    is going to come back for it, because every later firing is decided `noop`
    exactly as this one was.

    `confirm` then finishes what the kill interrupted, WITHOUT A CHALLENGE — the
    challenge is deleted first, exactly as the reboot this case models clears the
    tmpfs runtime root. It enables and starts the three guarded units, stops the
    dead-man last (until it is stopped, a run that died mid-way would be rolled
    back by it, and a committed run must never be) and moves the run to
    `confirmed`.
    """
    root = tmp_path
    fake = _arming_host(root=root)
    _drive_to_observed(root=root, host=fake)
    _ = _answer_the_challenge(root=root)
    _kill_at(fake=fake, seam="enable_units", after=1)
    with pytest.raises(RuntimeError):
        _ = _invoke(root=root, host=fake, argv=["confirm", _RUN])
    records = _module(name=_RECORDS_MODULE)
    model = _module(name=_MODEL_MODULE)
    state = _module(name=_STATE_MODULE)
    paths = _paths(root=root)
    assert state.read_marker(paths=paths, run=_RUN) == "self"
    assert _phase_of(root=root, run=_RUN) == "committed"

    refused = _arming_host(root=root)
    assert _invoke(root=root, host=refused, argv=["rollback", _RUN]) == 0

    for untouched in (
        "run_phase_child",
        "revoke_start_permission",
        "kill_cgroup",
        "disable_units",
        "restore_forward_policy",
        "read_postconditions",
    ):
        assert refused.calls_named(name=untouched) == (), untouched
    assert [call.detail[0] for call in refused.calls_named(name="stop_unit")] == [_DEADMAN_TIMER]
    assert _phase_of(root=root, run=_RUN) == "committed"
    assert state.read_marker(paths=paths, run=_RUN) == "self"

    finishing = _arming_host(root=root)
    records.challenge_path(paths=paths).unlink()
    assert records.read_challenge(paths=paths) is None

    assert _invoke(root=root, host=finishing, argv=["confirm", _RUN]) == 0

    assert finishing.calls_named(name="enable_units")[0].detail == model.GUARDED_UNITS
    assert [call.detail[0] for call in finishing.calls_named(name="start_unit")] == list(
        model.GUARDED_UNITS
    )
    assert [call.detail[0] for call in finishing.calls_named(name="stop_unit")] == [_DEADMAN_TIMER]
    assert _phase_of(root=root, run=_RUN) == "confirmed"
    assert finishing.calls_named(name="run_phase_child") == ()


def test_a_rollback_phase_that_keeps_killing_the_driver_does_not_stop_the_later_phases(
    tmp_path: Path,
) -> None:
    """Scenario: a rollback phase that keeps killing the driver does not stop the rest.

    The dead-man fires `rollback` four times and the job-cancellation phase's
    child takes the driver down on every entry. The first three firings each end
    there having written no outcome, leaving the run `rolling-back` — which is
    the phase the first firing recorded before it did anything else, and which
    every later firing must keep until one of them writes an outcome, because
    that record is what an operator reads while deciding whether the host needs a
    repair.

    The fourth firing SKIPS the phase, its recorded attempts having reached
    three, and runs every phase after it. That bound is the whole point: the
    FORWARD-policy restore and the interface deletion come after the job
    cancellation, and a parser that crashes the same way every time must not be
    able to stand between the dead-man and the access those two protect. The
    attempt is recorded BEFORE the phase is entered, which is what makes the
    count advance at all across firings that never return.
    """
    root = tmp_path
    rollback = _module(name=_ROLLBACK_MODULE)
    attempts = root / "var" / "runs" / _RUN / "rollback" / "job-cancel.attempts"
    outcome = root / "var" / "runs" / _RUN / "rollback" / "outcome.json"
    started = _arming_host(root=root)
    _drive_to_started(root=root, host=started)

    for firing in (1, 2, 3):
        fake = _arming_host(root=root)
        _every_postcondition_holds(fake=fake)
        _kill_the_driver_at(fake=fake, phase="job-cancel")

        with pytest.raises(RuntimeError):
            _ = _invoke(root=root, host=fake, argv=["rollback", _RUN])

        spawned = [call.detail[-1] for call in fake.calls_named(name="run_phase_child")]
        assert spawned[-1] == "job-cancel", firing
        assert attempts.read_text(encoding="utf-8") == str(firing), firing
        assert fake.calls_named(name="read_postconditions") == (), firing
        assert not outcome.exists(), firing
        assert _phase_of(root=root, run=_RUN) == "rolling-back", firing

    fourth = _arming_host(root=root)
    _every_postcondition_holds(fake=fourth)
    _kill_the_driver_at(fake=fourth, phase="job-cancel")

    assert _invoke(root=root, host=fourth, argv=["rollback", _RUN]) == 0

    spawned = [call.detail[-1] for call in fourth.calls_named(name="run_phase_child")]
    assert "job-cancel" not in spawned
    later = rollback.ROLLBACK_PHASE_ORDER[rollback.ROLLBACK_PHASE_ORDER.index("job-cancel") + 1 :]
    assert [phase for phase in spawned if phase in later] == list(later)
    assert attempts.read_text(encoding="utf-8") == str(rollback.MAX_ATTEMPTS)
    recorded = json.loads(outcome.read_text(encoding="utf-8"))
    assert recorded["outcome"] == _phase_of(root=root, run=_RUN)
    assert recorded["outcome"] == "rolled-back"


def test_recover_resumes_an_interrupted_publish_and_rolls_back_any_other_run(
    tmp_path: Path,
) -> None:
    """Scenario: the guard's recover resumes an interrupted publish, and rolls back the rest.

    `publishing` is the ONE pre-commit phase a recovery can carry forward,
    because the install it interrupted is inert by construction: the guarded
    units' start condition names a start permission that does not exist yet, so
    nothing behind that install can run. Here the package step is killed, which
    leaves the run exactly where the scenario starts it — `publishing`, no commit
    marker, snapshot already taken.

    The resumed publish must KEEP that first snapshot. The snapshot is what a
    rollback compares against, so one retaken after a package step would record
    Docker's own footprint as the host's baseline and the cleanup could no longer
    tell the two apart. Its bytes are marked before the resume and read back
    after, so a re-take would be visible rather than merely uncounted.

    Every other uncommitted phase has GRANTED something, so the only safe
    direction is back: a `started` run reaches the rollback driver and lands on
    the rollback path, with no forward step left whatever its records say.
    """
    resumed_root = tmp_path / "interrupted-publish"
    snapshot = _interrupt_a_publish(root=resumed_root)

    resuming = _host(root=resumed_root)
    assert _invoke(root=resumed_root, host=resuming, argv=["recover", _RUN]) == 0

    assert resuming.calls_named(name="take_snapshot") == ()
    assert len(resuming.calls_named(name="install_packages")) == 1
    assert snapshot.read_text(encoding="utf-8") == _FIRST_SNAPSHOT
    assert _phase_of(root=resumed_root, run=_RUN) == "published"

    rolled_root = tmp_path / "started-run"
    started = _arming_host(root=rolled_root)
    _drive_to_started(root=rolled_root, host=started)
    recovering = _arming_host(root=rolled_root)
    _every_postcondition_holds(fake=recovering)

    assert _invoke(root=rolled_root, host=recovering, argv=["recover", _RUN]) == 0

    assert _phase_of(root=rolled_root, run=_RUN) == "rolled-back"
    assert not _paths(root=rolled_root).marker.exists()
    assert recovering.calls_named(name="revoke_start_permission") != ()
    rollback = _module(name=_ROLLBACK_MODULE)
    spawned = [call.detail[-1] for call in recovering.calls_named(name="run_phase_child")]
    assert spawned == list(rollback.ROLLBACK_PHASE_ORDER)
