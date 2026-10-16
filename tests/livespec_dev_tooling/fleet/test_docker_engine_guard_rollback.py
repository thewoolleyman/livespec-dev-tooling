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
from pathlib import Path
from typing import Any

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
