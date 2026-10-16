"""Tests for the Docker engine install guard's rollback driver (child 2).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Rollback". Governing design:
`docs/docker-engine-guard-design.md` — F1's rollback, R4's ordering, G5,
H2's stop-first rule and H6's bounds.

The driver is reached only through 1a's dispatch table and touches the
host only through the `HostOps` protocol, so every assertion here runs
against 1a's `FakeHost` with an injected clock and state roots, and no
real host action ever fires. The fake stamps each seam call with the
phase recorded when it arrived, which is what lets an ORDERING between a
durable record and a host action be asserted at all.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"
_GUARD_MODULE = "livespec_dev_tooling.fleet.docker_engine_guard"
_CLI_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_cli"
_HOSTOPS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_hostops"
_ROLLBACK_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_rollback"
_ROLLBACK_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_rollback.py")


def _fake(*, root: Path) -> Any:
    """A `FakeHost` rooted at `root`, with the two guard state roots under it."""
    fake_module = importlib.import_module(_FAKE_MODULE)
    return fake_module.FakeHost(state_root=root / "var", runtime_root=root / "run")


def _paths(*, root: Path) -> Any:
    """`GuardPaths` for the two state roots `_fake` also uses."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def _env(*, root: Path, host: Any) -> Any:
    """A `GuardEnv` over the same two state roots `_fake` and `_paths` use."""
    state = importlib.import_module(_STATE_MODULE)
    return state.GuardEnv(paths=_paths(root=root), host=host)


def _record_phase(*, root: Path, run: str, phase: str) -> None:
    """Put a reservation and a phase on disk the way the guard's records read."""
    state_root = root / "var"
    (state_root / "runs" / run).mkdir(parents=True, exist_ok=True)
    _ = (state_root / "run").write_text(run, encoding="utf-8")
    _ = (state_root / "runs" / run / "phase").write_text(phase, encoding="utf-8")


def _decision() -> Any:
    """The table's decision a rollback reaches the driver with."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.Decision(verdict="proceed", reason="rollback is allowed from started")


def _driver() -> Any:
    """The rollback driver, asserted to have replaced 1a's declared stub.

    1a shipped this module as a stub whose docstring says child 2
    replaces the file and whose entry raises, so the stub marker's
    absence is the first thing each assertion here can read: it fails on
    the stub and passes on the driver, which is a genuine assertion
    rather than an unimportable module.
    """
    assert _ROLLBACK_PATH.is_file()
    assert "CHILD 2 REPLACES THIS FILE" not in _ROLLBACK_PATH.read_text(encoding="utf-8")
    return importlib.import_module(_ROLLBACK_MODULE)


def _phase_of(*, root: Path, run: str) -> Any:
    """The run's recorded phase, read the way every guard operation reads it."""
    state = importlib.import_module(_STATE_MODULE)
    return state.read_phase(paths=_paths(root=root), run=run)


# The two phases a firing may REPLACE the recorded phase with. Anything
# else a firing leaves behind is a phase it overwrote without having
# reached an outcome, which is the one thing a later firing must not do.
_OUTCOME_PHASES = ("rolled-back", "rollback-partial")


def test_rollback_records_rolling_back_first_and_closes_start_and_confirm(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": `rolling-back` is recorded before any other step.

    The record is what closes the forward path: from the first
    `rolling-back` on, `start` and `confirm` are allowed from phases this
    run no longer has, so neither can act on it again. Recording it
    BEFORE anything else is what makes that true even of a driver killed
    immediately afterwards — the alternative is a run that was acted on
    and still looks startable.
    """
    rollback = _driver()
    guard = importlib.import_module(_GUARD_MODULE)
    fake = _fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")

    outcome = rollback.run_rollback(
        run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision()
    )

    assert outcome.operation == "rollback"
    assert outcome.exit_code == 0
    # The fake stamps every seam call with the phase recorded when it
    # arrived, so the phase in force at the driver's FIRST host action is
    # the proof that the record came before it — and it stays the proof
    # once the driver writes an outcome over `rolling-back`.
    assert fake.calls[0].phase == "rolling-back"
    for closed in ("start", "confirm"):
        refused = guard.run_operation(
            operation=closed, run="run-a", env=_env(root=tmp_path, host=fake)
        )
        assert refused.verdict == "refuse", closed


def test_a_later_firing_keeps_the_recorded_phase_until_it_writes_an_outcome(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": a firing on the rollback path keeps the phase.

    The dead-man re-fires every 60 seconds after each rollback it runs,
    so most firings arrive on a run that is already `rolling-back` or
    already `rollback-partial`. A firing that re-recorded `rolling-back`
    over a `rollback-partial` would erase the one record an operator
    reads while deciding whether the host needs a repair, and would do
    it silently. The phase a firing leaves behind is therefore either the
    phase it came in with or the outcome it reached, never a third thing.
    """
    rollback = _driver()

    for incoming in ("rolling-back", "rollback-partial"):
        root = tmp_path / incoming
        fake = _fake(root=root)
        _record_phase(root=root, run="run-a", phase=incoming)

        _ = rollback.run_rollback(run="run-a", env=_env(root=root, host=fake), decision=_decision())

        kept = _phase_of(root=root, run="run-a")
        assert kept == incoming or kept in _OUTCOME_PHASES, incoming


def test_rollback_stops_the_observer_and_the_starter_before_revoking_the_permission(
    tmp_path: Path,
) -> None:
    """Specification "Rollback" / design H2: the two writers are fenced first.

    The observer holds a Docker API request and the starter is mid-start;
    either could still act on the daemon the revocation is meant to make
    unstartable. Revoking first and stopping second would leave a window
    in which a stopped-but-not-yet-inactive observer submits one more
    request, so the order is the content of the rule rather than tidiness.
    The 10 seconds is the SIGKILL the specification requires after the
    SIGTERM.
    """
    rollback = _driver()
    fake = _fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision())

    assert [(call.name, call.detail) for call in fake.calls][:3] == [
        ("stop_unit", ("docker-engine-guard-observe.service", "10")),
        ("stop_unit", ("docker-engine-guard-start.service", "10")),
        ("revoke_start_permission", ()),
    ]


# The specification's rollback order, written out rather than read from
# the driver, so a reordered table is a failing test rather than a test
# that agrees with whatever the code now says.
_SPECIFIED_ORDER = (
    "socket-stop",
    "job-cancel",
    "forward-restore",
    "cgroup-kill",
    "unit-disable",
    "footprint-removal",
    "interface-deletion",
    "sysctl-comparison",
)

# The three phases whose host action REPORTS something — a residual
# rule, a deleted interface, a sysctl that no longer matches the
# snapshot. The other five have nothing to hand back.
_REPORTING_PHASES = ("footprint-removal", "interface-deletion", "sysctl-comparison")


def _reporting_fake(*, root: Path) -> Any:
    """A `FakeHost` whose reporting seams answer, and with jobs queued.

    One of the queued jobs belongs to `k3s-agent.service`, which is how
    "cancel the guarded units' jobs by id, never a bare `systemctl
    cancel`" is asserted at all: the k3s job must survive.
    """
    hostops = importlib.import_module(_HOSTOPS_MODULE)
    fake = _fake(root=root)
    fake.jobs = (
        hostops.QueuedJob(job_id="41", unit="docker.service"),
        hostops.QueuedJob(job_id="42", unit="k3s-agent.service"),
        hostops.QueuedJob(job_id="43", unit="docker.socket"),
    )
    fake.firewall_residue = ("-A DOCKER -j ACCEPT",)
    fake.deleted_interfaces = ("docker0",)
    fake.sysctl_differences = ("net.ipv4.ip_forward 1 != 0",)
    return fake


def test_the_driver_spawns_one_child_per_phase_in_the_specified_order(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": the phase order, and all of it after the revocation.

    The order is not interchangeable. The socket stop precedes every
    service stop because a listening socket keeps re-triggering starts;
    the job cancellation precedes the kill because a queued start job
    would bring the daemon straight back; the FORWARD restore is early
    because it is the access-relevant one and takes milliseconds; the
    footprint, interface and sysctl phases come last because they are
    only meaningful once nothing is still writing rules.
    """
    rollback = _driver()
    assert "ROLLBACK_PHASE_ORDER" in rollback.__all__
    fake = _reporting_fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision())

    spawned = [call.detail[-1] for call in fake.calls_named(name="run_phase_child")]
    assert spawned == list(_SPECIFIED_ORDER)
    assert tuple(spawned) == rollback.ROLLBACK_PHASE_ORDER
    names = [call.name for call in fake.calls]
    assert names.index("revoke_start_permission") < names.index("run_phase_child")


def test_each_rollback_phase_takes_its_own_host_action_and_records_its_findings(
    tmp_path: Path,
) -> None:
    """Specification "Host actions": one phase, one bounded host action.

    Each phase runs in its own child process, so this is what that child
    does. The job cancellation is the one to read closely: it cancels
    the guarded units' jobs BY ID and leaves `k3s-agent.service`'s job
    alone, because a bare `systemctl cancel` would take the whole queue
    including k3s's. The kill targets only the two services and the
    sandbox slice, so no k3s process is reachable from here at all.
    """
    rollback = _driver()
    assert "run_phase" in rollback.__all__
    stop = "30"
    expected = {
        "socket-stop": [("stop_unit", ("docker.socket", stop))],
        "job-cancel": [("queued_jobs", ()), ("cancel_jobs", ("41", "43"))],
        "forward-restore": [("restore_forward_policy", ("before",))],
        "cgroup-kill": [
            ("kill_cgroup", ("docker.service", "containerd.service", "fabro-sandbox.slice")),
            ("stop_unit", ("docker.socket", stop)),
            ("stop_unit", ("docker.service", stop)),
            ("stop_unit", ("containerd.service", stop)),
            ("stop_unit", ("fabro-sandbox.slice", stop)),
        ],
        "unit-disable": [
            ("disable_units", ("containerd.service", "docker.service", "docker.socket"))
        ],
        "footprint-removal": [("remove_firewall_footprint", ("before",))],
        "interface-deletion": [("delete_bridge_interfaces", ())],
        "sysctl-comparison": [("compare_sysctls", ("before",))],
    }
    assert tuple(expected) == _SPECIFIED_ORDER

    for phase, calls in expected.items():
        root = tmp_path / phase
        fake = _reporting_fake(root=root)
        _record_phase(root=root, run="run-a", phase="rolling-back")

        outcome = rollback.run_phase(run="run-a", env=_env(root=root, host=fake), phase=phase)

        assert outcome.exit_code == 0, phase
        observed = [
            (call.name, tuple(Path(part).name for part in call.detail))
            for call in fake.calls
            if call.name != "run_phase_child"
        ]
        assert observed == calls, phase
        findings = root / "var" / "runs" / "run-a" / "rollback" / f"{phase}.findings"
        assert findings.is_file() == (phase in _REPORTING_PHASES), phase


def test_the_phase_child_reaches_its_phase_through_the_guard_command_line(
    tmp_path: Path,
) -> None:
    """The argv the driver builds is the argv that routes, and nothing else.

    A driver that built a command line nothing could route would spawn
    eight children that each did nothing and reported success, so the
    two halves are asserted TOGETHER: the driver's own argv is parsed and
    run here exactly as the child process runs it. The route is
    deliberately past the dispatch table and past the lock — the driver
    that spawned the child holds that lock, and a child waiting for it
    would block for its whole budget and then be killed having done
    nothing.
    """
    rollback = _driver()
    assert "phase_child_argv" in rollback.__all__
    guard = importlib.import_module(_GUARD_MODULE)
    cli = importlib.import_module(_CLI_MODULE)
    fake = _reporting_fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="rolling-back")
    argv = list(
        rollback.phase_child_argv(
            run="run-a", env=_env(root=tmp_path, host=fake), phase="unit-disable"
        )
    )

    code = guard.run_request(
        request=cli.parse_request(argv=argv[argv.index("rollback") :]), host=fake
    )

    assert code == 0
    assert fake.calls_named(name="disable_units")[0].detail == (
        "containerd.service",
        "docker.service",
        "docker.socket",
    )
    # A phase name that is not one of the eight is an expected refusal
    # carried on the outcome rail, never a raise: these modules run on a
    # bare host interpreter where the Result railway is not importable.
    refused = rollback.run_phase(run="run-a", env=_env(root=tmp_path, host=fake), phase="nope")
    assert refused.verdict == "refuse"
    assert refused.exit_code == 1


# The specification's postcondition set, written out here so a renamed
# or dropped postcondition is a failing test rather than a silently
# narrower final check.
_SPECIFIED_POSTCONDITIONS = (
    "no start permission",
    "no socket, process, queued job or pending start for the guarded units",
    "each FORWARD policy as snapshotted",
    "no Docker rule",
    "no docker0",
    "each watched sysctl as snapshotted",
)


def test_the_final_check_reads_every_postcondition_together_after_the_stop_phases(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": ONE read, after every stop phase, of all of them.

    Read earlier or phase by phase, each answer would be about a host
    something was still writing to: a `docker0` read while the daemon is
    being killed says nothing about whether the bridge is gone, and a
    rule set read before the footprint phase says nothing at all. One
    read after every writer has stopped is what makes the outcome a fact
    rather than a race.
    """
    rollback = _driver()
    assert "POSTCONDITIONS" in rollback.__all__
    assert rollback.POSTCONDITIONS == _SPECIFIED_POSTCONDITIONS
    fake = _reporting_fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision())

    reads = fake.calls_named(name="read_postconditions")
    assert len(reads) == 1
    assert reads[0].detail == (str(tmp_path / "var" / "runs" / "run-a" / "before"),)
    names = [call.name for call in fake.calls]
    last_phase = max(index for index, name in enumerate(names) if name == "run_phase_child")
    assert names.index("read_postconditions") > last_phase


def _rollback_record(*, root: Path, run: str, name: str) -> Path:
    """One of a run's rollback bookkeeping files: an attempt, a success, an outcome."""
    return root / "var" / "runs" / run / "rollback" / name


def _attempts_at_entry(*, fake: Any, root: Path, run: str) -> dict[str, str]:
    """Read each phase's attempt record AT THE MOMENT its child is spawned.

    The ordering between the durable record and the spawn is the whole
    assertion, and it cannot be read after the fact: a driver that
    recorded the attempt after spawning would leave identical files
    behind. Reading the record from inside the spawn is what tells the
    two apart — and it is exactly what a phase child that kills the
    driver sees.
    """
    seen: dict[str, str] = {}
    spawn = fake.run_phase_child

    def recording_spawn(*, argv: tuple[str, ...]) -> bool:
        record = _rollback_record(root=root, run=run, name=f"{argv[-1]}.attempts")
        seen[argv[-1]] = record.read_text(encoding="utf-8") if record.is_file() else "absent"
        return spawn(argv=argv)

    fake.run_phase_child = recording_spawn
    return seen


def test_the_driver_records_a_phase_attempt_durably_before_it_enters_the_phase(
    tmp_path: Path,
) -> None:
    """Specification "Rollback" / design H6: the attempt is recorded, then entered.

    The order is the only thing that makes the attempt budget work at
    all. A phase that kills the driver every time it is entered never
    returns to record anything, so an attempt recorded AFTER the spawn
    would never be written for exactly the phase the budget exists to
    bound — and the dead-man would re-enter it forever. Recorded first,
    the same crash still advances the count.
    """
    rollback = _driver()
    fake = _reporting_fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")
    seen = _attempts_at_entry(fake=fake, root=tmp_path, run="run-a")

    _ = rollback.run_rollback(run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision())

    assert seen == {phase: "1" for phase in _SPECIFIED_ORDER}


def test_every_phase_child_runs_under_timeout_with_that_phases_budget(
    tmp_path: Path,
) -> None:
    """Specification "Rollback" / design H6: `timeout -k 10 <phase budget>`.

    The wrapper is what makes a phase that HANGS cost its own budget and
    nothing more: SIGTERM at the budget, SIGKILL ten seconds later, and
    the driver gets a status back either way instead of blocking until
    its own transient unit is killed with no verdict at all. The budget
    is read from the driver's own table rather than written out here —
    the apportionment is its own rule, asserted on its own.
    """
    rollback = _driver()
    assert "PHASE_BUDGET_SECONDS" in rollback.__all__
    assert tuple(rollback.PHASE_BUDGET_SECONDS) == rollback.ROLLBACK_PHASE_ORDER
    assert all(budget > 0 for budget in rollback.PHASE_BUDGET_SECONDS.values())
    fake = _reporting_fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision())

    spawned = fake.calls_named(name="run_phase_child")
    assert len(spawned) == len(_SPECIFIED_ORDER)
    for call in spawned:
        phase = call.detail[-1]
        budget = str(rollback.PHASE_BUDGET_SECONDS[phase])
        assert call.detail[:4] == ("timeout", "-k", "10", budget), phase


def test_the_phase_budgets_are_apportioned_and_sum_to_six_hundred_seconds(
    tmp_path: Path,
) -> None:
    """Design H6: the phase budgets sum to 600 s of the 900 s rollback budget.

    The remaining 300 s is what the lock wait and the final
    all-postconditions check run in. That is the whole reason the sum is
    a rule: eight phases that each took their own generous bound would
    leave the final check to be SIGKILLed by the rollback unit's own
    `TimeoutStartSec`, and a rollback killed before its final check
    writes no outcome at all.

    The apportionment is not flat. The footprint phase parses and deletes
    rules in up to three passes with a per-command `iptables -w 5`, so it
    carries half the total; the socket stop and the job cancellation are
    single `systemctl` calls and take the floor.
    """
    rollback = _driver()
    model = importlib.import_module(_MODEL_MODULE)
    budgets = rollback.PHASE_BUDGET_SECONDS

    assert sum(budgets.values()) == 600
    rollback_budget = model.operation_budget_seconds(operation="rollback", window_seconds=0)
    assert rollback_budget - sum(budgets.values()) == 300
    assert budgets["footprint-removal"] == max(budgets.values())
    assert budgets["footprint-removal"] == 300
    assert budgets["cgroup-kill"] == 120
    assert min(budgets.values()) == 30
    # The paid-for bound reaches the command line unchanged.
    fake = _reporting_fake(root=tmp_path)
    _record_phase(root=tmp_path, run="run-a", phase="started")
    argv = rollback.phase_child_argv(
        run="run-a", env=_env(root=tmp_path, host=fake), phase="footprint-removal"
    )
    assert argv[:4] == ("timeout", "-k", "10", "300")


def _kill_driver_at(*, fake: Any, phase: str) -> None:
    """Make the phase child for `phase` take the whole driver down with it.

    A `RuntimeError` out of the seam is how a driver KILLED mid-phase is
    modelled: the driver has no handler for it, so the firing ends where
    the kill landed, having written whatever it had already written and
    no outcome at all. That is the state the next dead-man firing finds,
    and the only thing that advances across those firings is the attempt
    record the driver wrote before entering.

    The child is SPAWNED first and kills the driver second, which is the
    real sequence: the phase WAS entered, and it is the entry the attempt
    budget counts.
    """
    spawn = fake.run_phase_child

    def killing_spawn(*, argv: tuple[str, ...]) -> bool:
        completed = spawn(argv=argv)
        if argv[-1] == phase:
            raise RuntimeError(f"the {phase} child killed the driver")
        return completed

    fake.run_phase_child = killing_spawn


def test_a_phase_that_keeps_killing_the_driver_is_skipped_after_three_attempts(
    tmp_path: Path,
) -> None:
    """Acceptance scenario: a phase that keeps killing the driver is bounded.

    "Given a run in phase `rolling-back` whose job-cancellation phase
    kills the rollback driver every time it is entered; when the dead-man
    fires `rollback` four times" — the first three firings each end in
    that phase with no outcome written, and the fourth skips it, having
    reached three recorded attempts without a recorded success, and runs
    every later phase. A parser that crashes the same way every time can
    therefore delay the later phases by at most three firings rather
    than forever.
    """
    rollback = _driver()
    assert "MAX_ATTEMPTS" in rollback.__all__
    assert rollback.MAX_ATTEMPTS == 3
    _record_phase(root=tmp_path, run="run-a", phase="rolling-back")
    attempts = _rollback_record(root=tmp_path, run="run-a", name="job-cancel.attempts")

    for firing in (1, 2, 3):
        fake = _reporting_fake(root=tmp_path)
        _kill_driver_at(fake=fake, phase="job-cancel")

        with pytest.raises(RuntimeError):
            _ = rollback.run_rollback(
                run="run-a", env=_env(root=tmp_path, host=fake), decision=_decision()
            )

        spawned = [call.detail[-1] for call in fake.calls_named(name="run_phase_child")]
        assert spawned[-1] == "job-cancel", firing
        assert attempts.read_text(encoding="utf-8") == str(firing), firing
        assert not fake.calls_named(name="read_postconditions"), firing
        assert _phase_of(root=tmp_path, run="run-a") == "rolling-back", firing

    fourth = _reporting_fake(root=tmp_path)
    _kill_driver_at(fake=fourth, phase="job-cancel")

    _ = rollback.run_rollback(
        run="run-a", env=_env(root=tmp_path, host=fourth), decision=_decision()
    )

    spawned = [call.detail[-1] for call in fourth.calls_named(name="run_phase_child")]
    assert "job-cancel" not in spawned
    later = _SPECIFIED_ORDER[_SPECIFIED_ORDER.index("job-cancel") + 1 :]
    assert [phase for phase in spawned if phase in later] == list(later)
    assert attempts.read_text(encoding="utf-8") == "3"
    assert fourth.calls_named(name="read_postconditions")


def _exhaust_attempts(*, root: Path, run: str, phase: str) -> None:
    """Pre-seed a phase's attempt record at the budget, with no success beside it."""
    record = _rollback_record(root=root, run=run, name=f"{phase}.attempts")
    record.parent.mkdir(parents=True, exist_ok=True)
    _ = record.write_text("3", encoding="utf-8")


def test_a_failed_timed_out_or_skipped_phase_never_stops_a_later_one(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": no phase stands between the driver and a later one.

    All three ways a phase can come to nothing are asserted together
    because the driver must not tell them apart. A non-zero exit and a
    `timeout` kill arrive at the seam identically — `False` — and a
    skipped phase never reaches the seam at all; in every case the driver
    records no success, enters the next phase, and still reaches its
    final check. The reason is the access it protects: the FORWARD
    restore and the interface deletion come after the kill, so a kill
    that failed must not be able to keep them from running.
    """
    rollback = _driver()

    failed = tmp_path / "failed"
    fake = _reporting_fake(root=failed)
    fake.failing_phase_children = {"forward-restore"}
    # Every postcondition but the restored FORWARD policy holds, so the
    # final check clears nothing the successful phases recorded and the
    # success records still say which children completed.
    fake.postconditions = _postconditions_except(failing="each FORWARD policy as snapshotted")
    _record_phase(root=failed, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=failed, host=fake), decision=_decision())

    assert [call.detail[-1] for call in fake.calls_named(name="run_phase_child")] == list(
        _SPECIFIED_ORDER
    )
    assert not _rollback_record(root=failed, run="run-a", name="forward-restore.success").is_file()
    assert _rollback_record(root=failed, run="run-a", name="cgroup-kill.success").is_file()
    assert fake.calls_named(name="read_postconditions")

    skipped = tmp_path / "skipped"
    other = _reporting_fake(root=skipped)
    _record_phase(root=skipped, run="run-a", phase="rolling-back")
    _exhaust_attempts(root=skipped, run="run-a", phase="cgroup-kill")

    _ = rollback.run_rollback(run="run-a", env=_env(root=skipped, host=other), decision=_decision())

    spawned = [call.detail[-1] for call in other.calls_named(name="run_phase_child")]
    assert "cgroup-kill" not in spawned
    later = _SPECIFIED_ORDER[_SPECIFIED_ORDER.index("cgroup-kill") + 1 :]
    assert [phase for phase in spawned if phase in later] == list(later)
    assert other.calls_named(name="read_postconditions")


# The postcondition four phases share: the socket stop, the job
# cancellation, the cgroup kill and the unit disable all exist to make
# the guarded units quiet, so any of them failing shows up here.
_UNITS_POSTCONDITION = "no socket, process, queued job or pending start for the guarded units"


def _surviving_successes(*, root: Path, run: str) -> set[str]:
    """Every phase that still has a success record a later firing would trust."""
    return {
        phase
        for phase in _SPECIFIED_ORDER
        if _rollback_record(root=root, run=run, name=f"{phase}.success").is_file()
    }


def _postconditions_except(*, failing: str) -> dict[str, bool]:
    """A host postcondition record in which exactly `failing` does not hold."""
    return {name: name != failing for name in _SPECIFIED_POSTCONDITIONS}


def test_the_final_check_clears_the_success_of_every_failing_postcondition(
    tmp_path: Path,
) -> None:
    """Design H6: a postcondition that REGRESSES makes its phase eligible again.

    A success record is what a later firing trusts to skip a phase, so a
    stale one is the one way this driver could leave a host unrepaired
    while reporting that it had tried: the phase ran, something undid its
    work, and every firing after that skipped it. Clearing the record
    against the final check closes that, and it closes it for all four
    phases that share the guarded-units postcondition, because the check
    cannot tell which of them the regression belongs to.
    """
    rollback = _driver()
    assert "POSTCONDITION_OF_PHASE" in rollback.__all__
    owners = rollback.POSTCONDITION_OF_PHASE
    assert tuple(owners) == _SPECIFIED_ORDER
    assert set(owners.values()) <= set(_SPECIFIED_POSTCONDITIONS)
    assert [phase for phase, name in owners.items() if name == _UNITS_POSTCONDITION] == [
        "socket-stop",
        "job-cancel",
        "cgroup-kill",
        "unit-disable",
    ]

    one = tmp_path / "one"
    fake = _reporting_fake(root=one)
    fake.postconditions = _postconditions_except(failing="no docker0")
    _record_phase(root=one, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=one, host=fake), decision=_decision())

    assert _surviving_successes(root=one, run="run-a") == set(_SPECIFIED_ORDER) - {
        "interface-deletion"
    }

    shared = tmp_path / "shared"
    other = _reporting_fake(root=shared)
    other.postconditions = _postconditions_except(failing=_UNITS_POSTCONDITION)
    _record_phase(root=shared, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=shared, host=other), decision=_decision())

    assert _surviving_successes(root=shared, run="run-a") == {
        "forward-restore",
        "footprint-removal",
        "interface-deletion",
        "sysctl-comparison",
    }


def test_rolled_back_is_written_only_when_every_postcondition_holds(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": `rolled-back` is the claim, so it must be earned.

    `rolled-back` is final, and it is what makes every later dead-man
    firing a no-op and what lets a later `reserve` take the host again.
    Written while one postcondition still failed it would retire the
    dead-man over a host that still has a Docker rule or a `docker0`, and
    nothing would come back to look. So it is written only when the final
    check finds all six holding — and when one does not, the run is left
    on the rollback path for the next firing.
    """
    rollback = _driver()

    clean = tmp_path / "clean"
    fake = _reporting_fake(root=clean)
    fake.postconditions = dict.fromkeys(_SPECIFIED_POSTCONDITIONS, True)
    _record_phase(root=clean, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=clean, host=fake), decision=_decision())

    assert _phase_of(root=clean, run="run-a") == "rolled-back"

    for failing in _SPECIFIED_POSTCONDITIONS:
        root = tmp_path / failing.replace(" ", "-")[:24]
        other = _reporting_fake(root=root)
        other.postconditions = _postconditions_except(failing=failing)
        _record_phase(root=root, run="run-a", phase="started")

        _ = rollback.run_rollback(
            run="run-a", env=_env(root=root, host=other), decision=_decision()
        )

        assert _phase_of(root=root, run="run-a") != "rolled-back", failing


def test_rollback_partial_is_written_naming_each_failed_postcondition(
    tmp_path: Path,
) -> None:
    """Specification "Rollback": the partial outcome NAMES what still fails.

    An operator reaching a `rollback-partial` host is deciding whether to
    repair it by hand over Tailscale, and "something failed" does not
    support that decision: a residual Docker rule, a surviving `docker0`
    and a sysctl that no longer matches the snapshot need three different
    repairs. The names are therefore recorded durably beside the run,
    where a later `verify` reads them, as well as reported to whoever ran
    the firing.
    """
    rollback = _driver()

    for failing in ("no Docker rule", "no docker0"):
        root = tmp_path / failing.replace(" ", "-")
        fake = _reporting_fake(root=root)
        fake.postconditions = _postconditions_except(failing=failing)
        _record_phase(root=root, run="run-a", phase="started")

        outcome = rollback.run_rollback(
            run="run-a", env=_env(root=root, host=fake), decision=_decision()
        )

        assert _phase_of(root=root, run="run-a") == "rollback-partial", failing
        recorded = json.loads(
            _rollback_record(root=root, run="run-a", name="outcome.json").read_text(
                encoding="utf-8"
            )
        )
        assert recorded == {
            "outcome": "rollback-partial",
            "failed_postconditions": [failing],
        }, failing
        assert failing in outcome.reason, failing
        assert outcome.exit_code == 0, failing

    clean = tmp_path / "clean"
    other = _reporting_fake(root=clean)
    other.postconditions = dict.fromkeys(_SPECIFIED_POSTCONDITIONS, True)
    _record_phase(root=clean, run="run-a", phase="started")

    _ = rollback.run_rollback(run="run-a", env=_env(root=clean, host=other), decision=_decision())

    assert json.loads(
        _rollback_record(root=clean, run="run-a", name="outcome.json").read_text(encoding="utf-8")
    ) == {"outcome": "rolled-back", "failed_postconditions": []}
