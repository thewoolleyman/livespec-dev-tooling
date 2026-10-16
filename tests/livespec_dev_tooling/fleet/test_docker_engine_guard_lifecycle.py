"""Tests for the Docker engine install guard's lifecycle half (child 1a).

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard". Governing design:
`docs/docker-engine-guard-design.md` (revisions 5 to 8 govern).

The guard is six factory-safe children sharing one module set; this file
covers 1a — the lock, the run directory and its phase records, the
deadline, the dispatch table, and the `reserve`, `publish`, `arm`,
`start` and `recover` operations. The host is reached only through the
`HostOps` protocol, so every assertion here runs against `FakeHost` with
an injected clock, boot id and state roots, and no real host action ever
fires.
"""

from __future__ import annotations

import fcntl
import importlib
import json
import stat
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_MODEL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_model.py")
_HOSTOPS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_hostops"
_HOSTOPS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_hostops.py")
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"
_FAKE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_fake.py")
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_STATE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_state.py")
_GUARD_MODULE_UNDER_TEST = "livespec_dev_tooling.fleet.docker_engine_guard"
_ROLLBACK_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_rollback"
_HOST_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_host"
_PACKAGES_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_packages"
_OPS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_ops"
_OPS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_ops.py")

# The observation window the design derives at preflight from the effective
# k3s resync periods (420 s at the measured defaults). Only `observe`'s
# budget reads it; every other operation's budget is a flat number.
_WINDOW_SECONDS = 420


def test_the_operation_budget_table_gives_each_operation_its_timeout_start_sec() -> None:
    """Design H6: every bound stated, and `observe` alone adds the window.

    These are the `TimeoutStartSec` values the role passes to each
    operation's transient oneshot unit, so a wrong number here is a guard
    that systemd kills mid-rollback rather than a test that merely
    disagrees with a table.
    """
    assert _MODEL_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    budgets = {
        operation: model.operation_budget_seconds(
            operation=operation, window_seconds=_WINDOW_SECONDS
        )
        for operation in model.OPERATIONS
    }

    assert budgets == {
        "reserve": 60,
        "publish": 1800,
        "arm": 60,
        "start": 180,
        "observe": _WINDOW_SECONDS + 300,
        "confirm": 120,
        "rollback": 900,
        "recover": 1800,
        "verify": 120,
        "reconfigure": 120,
    }


def test_the_phase_vocabulary_names_both_paths_and_keeps_them_disjoint() -> None:
    """Specification section "Phases": nine install phases, three rollback phases.

    `observing` is the phase 1b's `observe` claims from `started` before its
    first sample, so it belongs to the install path even though nothing in
    1a transitions into it.
    """
    assert _MODEL_PATH.is_file()
    model = importlib.import_module(_MODEL_MODULE)

    assert model.INSTALL_PHASES == (
        "reserved",
        "publishing",
        "published",
        "armed",
        "started",
        "observing",
        "observed",
        "committed",
        "confirmed",
    )
    assert model.ROLLBACK_PHASES == ("rolling-back", "rolled-back", "rollback-partial")
    assert set(model.INSTALL_PHASES).isdisjoint(model.ROLLBACK_PHASES)
    assert model.PHASES == model.INSTALL_PHASES + model.ROLLBACK_PHASES


def _fake(*, root: Path) -> Any:
    """A `FakeHost` rooted at `root`, with the two guard state roots under it."""
    fake_module = importlib.import_module(_FAKE_MODULE)
    return fake_module.FakeHost(state_root=root / "var", runtime_root=root / "run")


def _record_phase(*, root: Path, run: str, phase: str) -> None:
    """Put a reservation and a phase on disk the way the guard's records read."""
    state_root = root / "var"
    (state_root / "runs" / run).mkdir(parents=True, exist_ok=True)
    (state_root / "run").write_text(run, encoding="utf-8")
    (state_root / "runs" / run / "phase").write_text(phase, encoding="utf-8")


def test_the_fake_host_implements_every_seam_the_host_ops_protocol_declares(
    tmp_path: Path,
) -> None:
    """The fake is the shared harness all six guard children test against.

    1b's `sample` and child 2's rollback-phase seams are declared here even
    though nothing in 1a calls them, precisely so that no sibling has to
    reopen `docker_engine_guard.py` to add one later.
    """
    assert _HOSTOPS_PATH.is_file()
    assert _FAKE_PATH.is_file()
    hostops = importlib.import_module(_HOSTOPS_MODULE)

    declared = {name for name in dir(hostops.HostOps) if not name.startswith("_")}
    assert declared >= {
        "boot_id",
        "cancel_jobs",
        "compare_sysctls",
        "condition_check_passed",
        "deadman_timer_active",
        "deadman_timer_exists",
        "delete_bridge_interfaces",
        "disable_units",
        "docker_group_members",
        "grant_start_permission",
        "guard_unit_states",
        "install_packages",
        "invoking_unit",
        "kill_cgroup",
        "monotonic",
        "queued_jobs",
        "read_postconditions",
        "remove_firewall_footprint",
        "restore_forward_policy",
        "revoke_start_permission",
        "sample",
        "set_owner_root",
        "sleep",
        "start_unit",
        "stop_unit",
        "systemd_run",
        "take_snapshot",
    }
    assert declared <= set(dir(_fake(root=tmp_path)))


def test_the_fake_host_records_each_seam_call_with_the_phase_in_force_then(
    tmp_path: Path,
) -> None:
    """Call ordering against the phase record is what 1a's own assertions read.

    `start` must reach `started` BEFORE it grants the start permission, and
    `publish` must reach `publishing` BEFORE its package step; both are
    orderings between a durable record and a host call, so the fake stamps
    every call with the phase that was recorded when it arrived.
    """
    assert _FAKE_PATH.is_file()
    fake = _fake(root=tmp_path)

    fake.boot_id()
    _record_phase(root=tmp_path, run="run-a", phase="publishing")
    fake.take_snapshot(destination=tmp_path / "before")
    _record_phase(root=tmp_path, run="run-a", phase="started")
    fake.grant_start_permission()
    fake.start_unit(unit="containerd.service", timeout_seconds=60)

    assert [(call.name, call.phase) for call in fake.calls] == [
        ("boot_id", None),
        ("take_snapshot", "publishing"),
        ("grant_start_permission", "started"),
        ("start_unit", "started"),
    ]
    assert fake.calls_named(name="start_unit")[0].detail == ("containerd.service", "60")


def test_the_fake_host_answers_the_seams_children_1b_and_2_will_drive(
    tmp_path: Path,
) -> None:
    """Every declared seam answers and records, so no sibling edits the fake's shape.

    The values are injected rather than computed: 1a ships no real host
    action, so the fake's job is to record the call and hand back whatever
    the test decided the host would say.
    """
    assert _FAKE_PATH.is_file()
    hostops = importlib.import_module(_HOSTOPS_MODULE)
    fake = _fake(root=tmp_path)
    fake.sample_result = {"node_ready": True}
    fake.firewall_residue = ("DOCKER rule",)
    fake.deleted_interfaces = ("docker0",)
    fake.sysctl_differences = ("net.ipv4.ip_forward",)
    fake.postconditions = {"no start permission": True}
    fake.jobs = (hostops.QueuedJob(job_id="41", unit="docker.service"),)
    snapshot = tmp_path / "before"

    assert fake.sample() == {"node_ready": True}
    assert fake.remove_firewall_footprint(snapshot=snapshot) == ("DOCKER rule",)
    assert fake.delete_bridge_interfaces() == ("docker0",)
    assert fake.compare_sysctls(snapshot=snapshot) == ("net.ipv4.ip_forward",)
    assert fake.read_postconditions(snapshot=snapshot) == {"no start permission": True}
    assert fake.queued_jobs() == (hostops.QueuedJob(job_id="41", unit="docker.service"),)
    fake.revoke_start_permission()
    fake.stop_unit(unit="docker.socket", timeout_seconds=30)
    fake.cancel_jobs(job_ids=("41",))
    fake.restore_forward_policy(snapshot=snapshot)
    fake.kill_cgroup(units=("docker.service",))
    fake.disable_units(units=("docker.service",))

    assert [call.name for call in fake.calls] == [
        "sample",
        "remove_firewall_footprint",
        "delete_bridge_interfaces",
        "compare_sysctls",
        "read_postconditions",
        "queued_jobs",
        "revoke_start_permission",
        "stop_unit",
        "cancel_jobs",
        "restore_forward_policy",
        "kill_cgroup",
        "disable_units",
    ]


def test_the_fake_host_answers_the_admission_clock_and_package_seams(
    tmp_path: Path,
) -> None:
    """The seams 1a's own decisions read, each injected and each recorded."""
    assert _FAKE_PATH.is_file()
    fake = _fake(root=tmp_path)
    fake.clock = 12.5
    fake.boot = "boot-b"
    fake.unit_states = {"docker-engine-guard-start.service": "failed"}
    fake.docker_group = ("ci",)
    fake.deadman_units = {"docker-engine-deadman-run-a"}
    fake.active_deadman_units = {"docker-engine-deadman-run-a"}
    fake.condition_check = False

    assert fake.monotonic() == 12.5
    fake.sleep(seconds=2.5)
    assert fake.monotonic() == 15.0
    assert fake.boot_id() == "boot-b"
    assert fake.guard_unit_states() == {"docker-engine-guard-start.service": "failed"}
    assert fake.invoking_unit() == fake.unit_of_invocation
    assert fake.docker_group_members() == ("ci",)
    assert fake.deadman_timer_exists(run="run-a") is True
    assert fake.deadman_timer_active(run="run-a") is True
    assert fake.deadman_timer_exists(run="run-b") is False
    assert fake.condition_check_passed() is False
    fake.set_owner_root(path=tmp_path / "run")
    fake.install_packages(inputs=tmp_path / "inputs")
    fake.systemd_run(argv=("systemd-run", "--collect"))

    assert fake.calls_named(name="systemd_run")[0].detail == ("systemd-run", "--collect")
    assert fake.calls_named(name="set_owner_root")[0].detail == (str(tmp_path / "run"),)


def _paths(*, root: Path) -> Any:
    """`GuardPaths` for the two state roots `_fake` also uses."""
    model = importlib.import_module(_MODEL_MODULE)
    return model.GuardPaths(state_root=root / "var", runtime_root=root / "run")


def test_the_guard_paths_name_every_durable_and_runtime_location(tmp_path: Path) -> None:
    """Specification scope: durable state under /var/lib, runtime state under /run.

    /run is tmpfs, so the start permission and the lock vanish on a reboot
    while the commit marker and the run records do not. The split is the
    whole reason a reboot before the commit point cannot start Docker.
    """
    model = importlib.import_module(_MODEL_MODULE)
    assert "GuardPaths" in model.__all__

    assert str(model.DEFAULT_STATE_ROOT) == "/var/lib/docker-engine-guard"
    assert str(model.DEFAULT_RUNTIME_ROOT) == "/run/docker-engine-guard"

    paths = _paths(root=tmp_path)
    var = tmp_path / "var"
    run = tmp_path / "run"
    assert paths.marker == var / "confirmed"
    assert paths.reservation == var / "run"
    assert paths.run_dir(run="run-a") == var / "runs" / "run-a"
    assert paths.phase_path(run="run-a") == var / "runs" / "run-a" / "phase"
    assert paths.deadline_path(run="run-a") == var / "runs" / "run-a" / "deadline.json"
    assert paths.snapshot_dir(run="run-a") == var / "runs" / "run-a" / "before"
    assert paths.inputs_dir(run="run-a") == var / "runs" / "run-a" / "inputs"
    assert paths.lock == run / "lock"
    assert paths.permission == run / "allow-start"


def test_a_durable_write_replaces_the_target_and_leaves_no_temporary_behind(
    tmp_path: Path,
) -> None:
    """Specification section "Phases": write, fsync, rename, then fsync the directory.

    A reader therefore sees a complete prior record or a complete new one,
    never a half-written phase. The observable halves are the ones asserted
    here: the rename lands, and no `.tmp` sibling survives to be mistaken
    for a record.
    """
    assert _STATE_PATH.is_file()
    state = importlib.import_module(_STATE_MODULE)
    target = tmp_path / "records" / "phase"

    state.write_durable(path=target, data="reserved")
    assert target.read_text(encoding="utf-8") == "reserved"

    state.write_durable(path=target, data="publishing")
    assert target.read_text(encoding="utf-8") == "publishing"
    assert sorted(p.name for p in target.parent.iterdir()) == ["phase"]


def test_the_phase_record_and_the_reservation_round_trip_through_the_run_directory(
    tmp_path: Path,
) -> None:
    """Each run records exactly one phase, in its own directory under the state root."""
    assert _STATE_PATH.is_file()
    state = importlib.import_module(_STATE_MODULE)
    paths = _paths(root=tmp_path)

    assert state.read_phase(paths=paths, run="run-a") is None
    assert state.read_reservation(paths=paths) is None

    state.record_phase(paths=paths, run="run-a", phase="reserved")
    state.write_reservation(paths=paths, run="run-a")
    assert state.read_phase(paths=paths, run="run-a") == "reserved"
    assert state.read_reservation(paths=paths) == "run-a"

    state.record_phase(paths=paths, run="run-a", phase="publishing")
    assert state.read_phase(paths=paths, run="run-a") == "publishing"


def test_the_commit_marker_reads_as_absent_self_other_or_unreadable(tmp_path: Path) -> None:
    """Specification dispatch table: the marker, not the phase, decides commitment.

    The three columns of that table are exactly these states, and an
    unreadable marker joins "names another run" rather than "absent" --
    fail-closed, because a marker that cannot be read is not evidence that
    no run committed.
    """
    assert _STATE_PATH.is_file()
    state = importlib.import_module(_STATE_MODULE)
    paths = _paths(root=tmp_path)
    paths.marker.parent.mkdir(parents=True, exist_ok=True)

    assert state.read_marker(paths=paths, run="run-a") == "absent"

    state.write_durable(path=paths.marker, data=json.dumps({"run": "run-a", "digest": "d"}))
    assert state.read_marker(paths=paths, run="run-a") == "self"
    assert state.read_marker(paths=paths, run="run-b") == "other"

    state.write_durable(path=paths.marker, data="{not json")
    assert state.read_marker(paths=paths, run="run-a") == "unreadable"
    state.write_durable(path=paths.marker, data="[]")
    assert state.read_marker(paths=paths, run="run-a") == "unreadable"
    state.write_durable(path=paths.marker, data=json.dumps({"digest": "d"}))
    assert state.read_marker(paths=paths, run="run-a") == "unreadable"


def test_a_deadline_recorded_under_another_boot_id_has_passed(tmp_path: Path) -> None:
    """Design H4: the deadline is a boot id plus a CLOCK_MONOTONIC instant.

    A monotonic instant means nothing across a reboot, so a differing boot
    id counts as passed outright -- which is what makes a reboot before the
    commit point end in a rollback rather than in a run that believes it
    still has time.
    """
    assert _STATE_PATH.is_file()
    state = importlib.import_module(_STATE_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    paths = _paths(root=tmp_path)
    fake = _fake(root=tmp_path)

    assert state.read_deadline(paths=paths, run="run-a") is None
    assert state.deadline_passed(deadline=None, host=fake) is True

    state.write_deadline(
        paths=paths, run="run-a", deadline=model.Deadline(boot_id="boot-a", monotonic=100.0)
    )
    recorded = state.read_deadline(paths=paths, run="run-a")
    assert recorded == model.Deadline(boot_id="boot-a", monotonic=100.0)

    fake.clock = 99.0
    assert state.deadline_passed(deadline=recorded, host=fake) is False
    fake.clock = 100.0
    assert state.deadline_passed(deadline=recorded, host=fake) is True

    fake.clock = 1.0
    fake.boot = "boot-b"
    assert state.deadline_passed(deadline=recorded, host=fake) is True


def test_the_runtime_directory_is_ensured_mode_0700_and_root_owned(tmp_path: Path) -> None:
    """Design I4: every helper first ensures /run/docker-engine-guard exists.

    /run is tmpfs, so after a reboot the directory is simply gone and the
    FIRST helper to run has to recreate it. Mode 0700 is set in-process;
    the ownership goes through the host seam, because 1a ships no real
    host action of its own.
    """
    state = importlib.import_module(_STATE_MODULE)
    assert "ensure_runtime_dir" in state.__all__
    paths = _paths(root=tmp_path)
    fake = _fake(root=tmp_path)

    assert not paths.runtime_root.exists()
    state.ensure_runtime_dir(paths=paths, host=fake)

    assert paths.runtime_root.is_dir()
    assert stat.S_IMODE(paths.runtime_root.stat().st_mode) == 0o700
    assert fake.calls_named(name="set_owner_root")[0].detail == (str(paths.runtime_root),)

    state.ensure_runtime_dir(paths=paths, host=fake)
    assert stat.S_IMODE(paths.runtime_root.stat().st_mode) == 0o700
    assert len(fake.calls_named(name="set_owner_root")) == 2


def test_the_lock_is_opened_with_o_creat_and_close_on_exec_and_never_replaced(
    tmp_path: Path,
) -> None:
    """Specification: open the lock with O_CREAT and close-on-exec, never unlink it.

    Close-on-exec matters because the guard spawns children: an inherited
    lock descriptor would keep the lock alive past the process that took
    it. Never unlinking matters because two helpers that each created
    their own lock file would each hold a lock on a different inode and
    both believe they were alone.
    """
    state = importlib.import_module(_STATE_MODULE)
    assert "acquire_lock" in state.__all__
    paths = _paths(root=tmp_path)
    fake = _fake(root=tmp_path)
    state.ensure_runtime_dir(paths=paths, host=fake)

    assert not paths.lock.exists()
    first = state.acquire_lock(paths=paths, host=fake)
    assert first is not None
    assert fcntl.fcntl(first, fcntl.F_GETFD) & fcntl.FD_CLOEXEC
    created_inode = paths.lock.stat().st_ino
    state.release_lock(fd=first)

    assert paths.lock.is_file()
    second = state.acquire_lock(paths=paths, host=fake)
    assert second is not None
    assert paths.lock.stat().st_ino == created_inode
    state.release_lock(fd=second)
    assert paths.lock.is_file()


def test_the_lock_wait_expires_after_sixty_seconds_without_acting(tmp_path: Path) -> None:
    """Specification: wait at most 60 seconds, then exit non-zero without acting.

    A guard that blocked forever on the lock would hold its transient
    unit open to its whole budget and be SIGKILLed with no verdict, which
    is indistinguishable from a refusal. Bounding the wait makes the
    refusal explicit and the run untouched.
    """
    state = importlib.import_module(_STATE_MODULE)
    assert "LOCK_WAIT_SECONDS" in state.__all__
    assert state.LOCK_WAIT_SECONDS == 60
    paths = _paths(root=tmp_path)
    fake = _fake(root=tmp_path)
    state.ensure_runtime_dir(paths=paths, host=fake)

    held = state.acquire_lock(paths=paths, host=fake)
    assert held is not None
    inode_while_held = paths.lock.stat().st_ino

    started = fake.clock
    assert state.acquire_lock(paths=paths, host=fake) is None
    assert fake.clock - started <= state.LOCK_WAIT_SECONDS
    assert fake.clock > started
    assert paths.lock.stat().st_ino == inode_while_held

    state.release_lock(fd=held)
    regained = state.acquire_lock(paths=paths, host=fake)
    assert regained is not None
    state.release_lock(fd=regained)


_OPERATIONS = (
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
)


def _guard_surface() -> Any:
    """The guard module, with the operation entry point this child owes it."""
    guard = importlib.import_module(_GUARD_MODULE_UNDER_TEST)
    assert "run_operation" in guard.__all__
    assert "sibling_module_name" in guard.__all__
    return guard


def _env(*, root: Path, host: Any) -> Any:
    """A `GuardEnv` over the same two state roots `_fake` and `_paths` use."""
    state = importlib.import_module(_STATE_MODULE)
    return state.GuardEnv(paths=_paths(root=root), host=host)


def _write_marker(*, root: Path, run: str) -> None:
    """Publish a commit marker naming `run`, the way `confirm` would."""
    state = importlib.import_module(_STATE_MODULE)
    paths = _paths(root=root)
    state.write_durable(path=paths.marker, data=json.dumps({"run": run, "digest": "d"}))


def _arm_deadline(*, root: Path, run: str, boot: str, at: float) -> None:
    """Record a deadline for `run` the way `arm` would."""
    state = importlib.import_module(_STATE_MODULE)
    model = importlib.import_module(_MODEL_MODULE)
    state.write_deadline(
        paths=_paths(root=root), run=run, deadline=model.Deadline(boot_id=boot, monotonic=at)
    )


def test_every_operation_ensures_the_runtime_directory_and_opens_the_one_lock(
    tmp_path: Path,
) -> None:
    """Design I4: the runtime directory and the lock come before any decision.

    Asserted for every operation rather than for one, because the
    specification states it of every operation and a helper that skipped
    it would work perfectly until the first reboot cleared /run.
    """
    guard = _guard_surface()

    for operation in _OPERATIONS:
        root = tmp_path / operation
        fake = _fake(root=root)
        _record_phase(root=root, run="run-a", phase="started")
        _write_marker(root=root, run="run-other")
        paths = _paths(root=root)

        outcome = guard.run_operation(
            operation=operation, run="run-a", env=_env(root=root, host=fake)
        )

        assert paths.runtime_root.is_dir()
        assert stat.S_IMODE(paths.runtime_root.stat().st_mode) == 0o700
        assert paths.lock.is_file()
        assert fake.calls_named(name="set_owner_root")[0].detail == (str(paths.runtime_root),)
        assert outcome.verdict == "refuse", operation
        assert outcome.exit_code == 1, operation


def test_every_operation_refuses_without_acting_when_the_lock_wait_expires(
    tmp_path: Path,
) -> None:
    """Specification: exit non-zero without acting once the 60-second wait expires.

    "Without acting" is the half worth asserting: the refusal must leave
    the reservation and the phase exactly as it found them, so a second
    controller that merely lost the race changes nothing.
    """
    state = importlib.import_module(_STATE_MODULE)
    guard = _guard_surface()

    for operation in _OPERATIONS:
        root = tmp_path / operation
        fake = _fake(root=root)
        paths = _paths(root=root)
        _record_phase(root=root, run="run-a", phase="started")
        state.ensure_runtime_dir(paths=paths, host=fake)
        held = state.acquire_lock(paths=paths, host=fake)
        assert held is not None

        outcome = guard.run_operation(
            operation=operation, run="run-a", env=_env(root=root, host=fake)
        )

        assert outcome.verdict == "refuse", operation
        assert outcome.exit_code == 1, operation
        assert state.read_reservation(paths=paths) == "run-a"
        assert state.read_phase(paths=paths, run="run-a") == "started"
        state.release_lock(fd=held)


def test_every_operation_on_a_run_that_is_not_the_current_reservation_refuses(
    tmp_path: Path,
) -> None:
    """Specification: an operation on a run that is not the current reservation refuses.

    `reserve` is the one operation that is not on the current run -- it
    is how a run becomes one -- so it is excluded here and governed by
    its own admission rule instead. The refusal names the holder, because
    an operator who reached the wrong host needs to know which run has it.
    """
    guard = _guard_surface()

    for operation in _OPERATIONS:
        if operation == "reserve":
            continue
        root = tmp_path / operation
        fake = _fake(root=root)
        _record_phase(root=root, run="run-a", phase="started")

        outcome = guard.run_operation(
            operation=operation, run="run-b", env=_env(root=root, host=fake)
        )

        assert outcome.verdict == "refuse", operation
        assert outcome.holder is not None
        assert outcome.holder.run == "run-a"
        assert outcome.holder.phase == "started"
        assert "run-a" in outcome.reason or outcome.holder.run == "run-a"


def test_a_deadline_from_an_earlier_boot_stops_start_from_granting_the_permission(
    tmp_path: Path,
) -> None:
    """Acceptance scenario: a deadline recorded on an earlier boot counts as passed.

    The run is `armed`, its dead-man timer is live and its monotonic
    instant is still far away -- the only thing wrong is the boot id, and
    that alone must stop it.
    """
    guard = _guard_surface()
    root = tmp_path / "earlier-boot"
    fake = _fake(root=root)
    fake.boot = "boot-b"
    fake.clock = 1.0
    fake.deadman_units = {"docker-engine-deadman-run-a"}
    fake.active_deadman_units = {"docker-engine-deadman-run-a"}
    _record_phase(root=root, run="run-a", phase="armed")
    _arm_deadline(root=root, run="run-a", boot="boot-a", at=10_000.0)

    outcome = guard.run_operation(operation="start", run="run-a", env=_env(root=root, host=fake))

    assert outcome.verdict == "refuse"
    assert not _paths(root=root).permission.exists()
    assert fake.calls_named(name="grant_start_permission") == ()


def test_the_operations_a_later_child_owns_reach_their_decision_and_stop_there(
    tmp_path: Path,
) -> None:
    """1b fills in observe, confirm, verify and reconfigure; 1a decides them.

    Each is driven into the state its row admits and must get PAST the
    table -- the `NotImplementedError` is the proof that the decision was
    reached, and that nothing but the work is missing.
    """
    guard = _guard_surface()
    admitted = {
        "observe": "started",
        "confirm": "observed",
        "verify": "rolled-back",
    }

    for operation, phase in admitted.items():
        root = tmp_path / operation
        fake = _fake(root=root)
        _record_phase(root=root, run="run-a", phase=phase)
        _arm_deadline(root=root, run="run-a", boot="boot-a", at=10_000.0)
        with pytest.raises(NotImplementedError):
            guard.run_operation(operation=operation, run="run-a", env=_env(root=root, host=fake))

    root = tmp_path / "reconfigure"
    fake = _fake(root=root)
    _record_phase(root=root, run="run-a", phase="confirmed")
    _write_marker(root=root, run="run-a")
    with pytest.raises(NotImplementedError):
        guard.run_operation(operation="reconfigure", run="run-a", env=_env(root=root, host=fake))


def test_rollback_hands_a_decided_run_to_child_two_and_no_ops_a_finished_one(
    tmp_path: Path,
) -> None:
    """Specification: rollback's entry decides here, and the driver lives next door.

    A committed run and an already rolled-back run both exit 0 having
    done nothing -- neither reaches the driver at all, which is what
    makes "a committed run is never rolled back" a property of the table
    rather than of the driver's good behaviour.
    """
    guard = _guard_surface()

    decided = tmp_path / "decided"
    fake = _fake(root=decided)
    _record_phase(root=decided, run="run-a", phase="started")
    with pytest.raises(NotImplementedError):
        guard.run_operation(operation="rollback", run="run-a", env=_env(root=decided, host=fake))

    committed = tmp_path / "committed"
    fake = _fake(root=committed)
    _record_phase(root=committed, run="run-a", phase="committed")
    _write_marker(root=committed, run="run-a")
    outcome = guard.run_operation(
        operation="rollback", run="run-a", env=_env(root=committed, host=fake)
    )
    assert outcome.verdict == "noop"
    assert outcome.exit_code == 0

    finished = tmp_path / "finished"
    fake = _fake(root=finished)
    _record_phase(root=finished, run="run-a", phase="rolled-back")
    outcome = guard.run_operation(
        operation="rollback", run="run-a", env=_env(root=finished, host=fake)
    )
    assert outcome.verdict == "noop"
    assert outcome.exit_code == 0


def test_the_sibling_stubs_each_sibling_replaces_are_present_and_unimplemented(
    tmp_path: Path,
) -> None:
    """Three stub modules, so no sibling ever has to reopen the guard module.

    Child 2 replaces the rollback driver, children 3a and 4 the real
    host, child 3b the package step. Each is reached by name from the
    guard module, which resolves siblings package-qualified when imported
    and bare when run as a script on the guarded host.
    """
    guard = _guard_surface()
    assert guard.sibling_module_name(package="pkg", name="_mod") == "pkg._mod"
    assert guard.sibling_module_name(package="", name="_mod") == "_mod"

    rollback = importlib.import_module(_ROLLBACK_MODULE)
    host_module = importlib.import_module(_HOST_MODULE)
    packages = importlib.import_module(_PACKAGES_MODULE)
    env = _env(root=tmp_path, host=_fake(root=tmp_path))
    model = importlib.import_module(_MODEL_MODULE)
    decision = model.Decision(verdict="proceed", reason="decided")

    with pytest.raises(NotImplementedError):
        rollback.run_rollback(run="run-a", env=env, decision=decision)
    with pytest.raises(NotImplementedError):
        host_module.build_real_host(paths=_paths(root=tmp_path))
    with pytest.raises(NotImplementedError):
        packages.run_package_step(inputs=tmp_path / "inputs")


def test_on_a_host_that_holds_no_reservation_only_reserve_gets_past_the_table(
    tmp_path: Path,
) -> None:
    """The boundary case of the reservation check: nothing holds the host at all.

    Every operation but `reserve` is an operation ON a run, so with no
    reservation recorded each refuses and reports no holder -- there is
    genuinely nobody to name, which is different from naming the wrong
    run and must read differently to an operator.
    """
    guard = _guard_surface()

    for operation in _OPERATIONS:
        if operation == "reserve":
            continue
        root = tmp_path / operation
        fake = _fake(root=root)

        outcome = guard.run_operation(
            operation=operation, run="run-a", env=_env(root=root, host=fake)
        )

        assert outcome.verdict == "refuse", operation
        assert outcome.holder is None, operation


_GUARD_UNITS_QUIET = {
    "docker-engine-guard-start.service": "inactive",
    "docker-engine-guard-observe.service": "inactive",
    "docker-engine-deadman-run-a.timer": "inactive",
    "docker-engine-deadman-run-a.service": "inactive",
}


def _ops_surface() -> Any:
    """The operations module, with the five entries child 1a owes the table."""
    assert _OPS_PATH.is_file()
    ops = importlib.import_module(_OPS_MODULE)
    assert "reserve" in ops.__all__
    return ops


def test_reserve_creates_the_reservation_on_a_quiet_unused_host(tmp_path: Path) -> None:
    """Design I1, the admitted case: no marker, no holder, no guard unit, no group.

    Reserving is what gives a controller the right to touch Docker on
    this host at all, so the inputs directory is created with it: the
    controller uploads only into its own run, and only `publish` ever
    installs anything from there.
    """
    _ops_surface()
    guard = _guard_surface()
    state = importlib.import_module(_STATE_MODULE)
    fake = _fake(root=tmp_path)
    fake.unit_states = dict(_GUARD_UNITS_QUIET)

    outcome = guard.run_operation(
        operation="reserve", run="run-a", env=_env(root=tmp_path, host=fake)
    )

    paths = _paths(root=tmp_path)
    assert outcome.exit_code == 0
    assert state.read_reservation(paths=paths) == "run-a"
    assert state.read_phase(paths=paths, run="run-a") == "reserved"
    assert paths.inputs_dir(run="run-a").is_dir()


def test_reserve_replaces_a_rolled_back_reservation_and_refuses_any_other(
    tmp_path: Path,
) -> None:
    """Design I1: the current reservation must be absent or `rolled-back`.

    A committed host is closed to the guarded transition entirely (H3),
    and a run still in a live phase keeps the host — those are the two
    ways a second controller is turned away, and neither changes a byte
    of the run it found.
    """
    _ops_surface()
    guard = _guard_surface()
    state = importlib.import_module(_STATE_MODULE)

    after_rollback = tmp_path / "after-rollback"
    fake = _fake(root=after_rollback)
    fake.unit_states = dict(_GUARD_UNITS_QUIET)
    _record_phase(root=after_rollback, run="run-a", phase="rolled-back")
    outcome = guard.run_operation(
        operation="reserve", run="run-b", env=_env(root=after_rollback, host=fake)
    )
    assert outcome.exit_code == 0
    assert state.read_reservation(paths=_paths(root=after_rollback)) == "run-b"

    committed = tmp_path / "committed"
    fake = _fake(root=committed)
    fake.unit_states = dict(_GUARD_UNITS_QUIET)
    _write_marker(root=committed, run="run-a")
    outcome = guard.run_operation(
        operation="reserve", run="run-b", env=_env(root=committed, host=fake)
    )
    assert outcome.verdict == "refuse"
    assert state.read_reservation(paths=_paths(root=committed)) is None

    busy = tmp_path / "busy"
    fake = _fake(root=busy)
    fake.unit_states = dict(_GUARD_UNITS_QUIET)
    _record_phase(root=busy, run="run-a", phase="observing")
    outcome = guard.run_operation(operation="reserve", run="run-b", env=_env(root=busy, host=fake))
    assert outcome.verdict == "refuse"
    assert state.read_reservation(paths=_paths(root=busy)) == "run-a"


def test_reserve_refuses_while_any_account_is_in_the_docker_group(tmp_path: Path) -> None:
    """Design F7 and I1: the Docker API is admitted to nobody but the guard.

    `docker.socket` is group-owned, so a single member of the `docker`
    group is a second party that could reach the daemon during the
    guarded window — and the window is precisely when nothing else may.
    """
    _ops_surface()
    guard = _guard_surface()
    state = importlib.import_module(_STATE_MODULE)
    fake = _fake(root=tmp_path)
    fake.unit_states = dict(_GUARD_UNITS_QUIET)
    fake.docker_group = ("ci",)

    outcome = guard.run_operation(
        operation="reserve", run="run-a", env=_env(root=tmp_path, host=fake)
    )

    assert outcome.verdict == "refuse"
    assert "ci" in outcome.reason
    assert state.read_reservation(paths=_paths(root=tmp_path)) is None
    # Nothing holds the host and no unit is busy, so the report is the
    # verdict line alone: a holder line naming nobody, or an empty
    # not-quiescent line, would each invite a wrong next step.
    assert outcome.report_lines() == (f"reserve refuse: {outcome.reason}",)


def test_a_refused_reserve_names_the_holding_run_its_phase_and_its_deadline(
    tmp_path: Path,
) -> None:
    """Acceptance scenario: a second controller cannot reserve while a run is unfinished.

    The refusal has to be actionable. The run id says which controller
    owns the host, the phase says how far it got, and the deadline is the
    only one of the three that tells an operator whether waiting is the
    right move or whether the dead-man has already been and gone.
    """
    _ops_surface()
    guard = _guard_surface()
    state = importlib.import_module(_STATE_MODULE)
    root = tmp_path / "second-controller"
    fake = _fake(root=root)
    fake.unit_states = dict(_GUARD_UNITS_QUIET)
    fake.deadman_units = {"docker-engine-deadman-run-a"}
    fake.active_deadman_units = {"docker-engine-deadman-run-a"}
    _record_phase(root=root, run="run-a", phase="observing")
    _arm_deadline(root=root, run="run-a", boot="boot-a", at=9_000.0)

    outcome = guard.run_operation(operation="reserve", run="run-b", env=_env(root=root, host=fake))

    assert outcome.verdict == "refuse"
    assert outcome.holder is not None
    assert outcome.holder.run == "run-a"
    assert outcome.holder.phase == "observing"
    assert outcome.holder.deadline is not None
    assert outcome.holder.deadline.boot_id == "boot-a"
    assert outcome.holder.deadline.monotonic == 9_000.0
    report = "\n".join(outcome.report_lines())
    assert "run-a" in report
    assert "observing" in report
    assert "boot-a" in report
    assert "9000" in report

    paths = _paths(root=root)
    assert state.read_reservation(paths=paths) == "run-a"
    assert state.read_phase(paths=paths, run="run-a") == "observing"
    assert state.read_deadline(paths=paths, run="run-a").monotonic == 9_000.0
    assert fake.deadman_timer_active(run="run-a") is True


def test_a_refused_reserve_names_each_guard_unit_found_in_the_failed_state(
    tmp_path: Path,
) -> None:
    """Design I1: a guard unit in `failed` is not `inactive`, and the refusal names it.

    "Quiescent" means inactive with no queued job. A failed dead-man
    service is the case worth naming explicitly: it means a rollback was
    attempted and did not finish, which is exactly when a fresh
    reservation would be most damaging.
    """
    _ops_surface()
    guard = _guard_surface()
    hostops = importlib.import_module(_HOSTOPS_MODULE)
    root = tmp_path / "units-busy"
    fake = _fake(root=root)
    fake.unit_of_invocation = "docker-engine-guard-reserve-run-b-1.service"
    fake.unit_states = {
        "docker-engine-guard-start.service": "inactive",
        "docker-engine-guard-observe.service": "activating",
        "docker-engine-deadman-run-a.service": "failed",
        "docker-engine-deadman-run-a.timer": "inactive",
        "docker-engine-guard-reserve-run-b-1.service": "activating",
    }
    fake.jobs = (hostops.QueuedJob(job_id="7", unit="docker-engine-guard-start.service"),)
    _record_phase(root=root, run="run-a", phase="rolled-back")

    outcome = guard.run_operation(operation="reserve", run="run-b", env=_env(root=root, host=fake))

    assert outcome.verdict == "refuse"
    assert outcome.blocking_units == (
        "docker-engine-deadman-run-a.service",
        "docker-engine-guard-observe.service",
        "docker-engine-guard-start.service",
    )
    report = "\n".join(outcome.report_lines())
    assert "docker-engine-deadman-run-a.service" in report
    assert "docker-engine-guard-reserve-run-b-1.service" not in report
    # The holder rolled back and so never armed a deadline. The report has
    # to say that in words rather than leave the field blank, which would
    # read as "no deadline has passed yet".
    assert "run-a" in report
    assert "none recorded" in report
