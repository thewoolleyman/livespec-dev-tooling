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

import importlib
import json
from pathlib import Path
from typing import Any

__all__: list[str] = []

_MODEL_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_model"
_MODEL_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_model.py")
_HOSTOPS_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_hostops"
_HOSTOPS_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_hostops.py")
_FAKE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_fake"
_FAKE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_fake.py")
_STATE_MODULE = "livespec_dev_tooling.fleet._docker_engine_guard_state"
_STATE_PATH = Path("livespec_dev_tooling/fleet/_docker_engine_guard_state.py")

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
